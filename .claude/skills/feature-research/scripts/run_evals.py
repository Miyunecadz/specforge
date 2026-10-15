#!/usr/bin/env python3
"""Offline pipeline evals (BUILD_SPEC §16). Run outside any Claude Code session.

    run_evals.py [--cases case-06 case-07 ...] [--model sonnet] [--dry-run] [--no-grader]
    run_evals.py --calibrate          # grader agreement on evals/grader-calibration/
    run_evals.py --until-stage 7      # smoke run: stop each case once Stage 7 completes

For each case, in config order and one at a time, it launches

    claude -p "/feature-research --non-interactive evals/cases/<case>/input.json"
      --permission-mode dontAsk --allowedTools Read Write Agent WebSearch "Bash(<py> <scripts>/*)"
      --setting-sources project --max-budget-usd <min(per case, remaining) - margin>

with FRA_EVAL_FIXTURES=evals/fixtures/<case> in the child environment only, so hooks H1-H5
stay active and checkpoint answers come from the case file through status_rules.py decide
--from-case. It never uses a permission mode that skips checks. A case that exhausts its
budget is reported blocked; a run left active is aborted with its artifacts kept.

Each case is scored by _lib/metrics.py (every metric with its numerator and denominator,
never one score). Findings that passed the mechanical citation check are then graded by the
eval-citation-grader agent (Read only; it returns JSON in its final message) and its scores
are reported separately. Results go to evals/results/<timestamp>.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import hashing, metrics, paths, runctx, schema  # noqa: E402
from _lib.fsutil import atomic_write_bytes  # noqa: E402
from _lib.runctx import now_iso  # noqa: E402

REPO = paths.REPO_ROOT


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))

MAX_NUDGES = 2
NUDGE = "Continue the non-interactive eval run from where it stopped; answers come only from the case file."
CALIBRATION_DIR = Path("evals/grader-calibration")
# Case-specific metrics that must be 1 for a case to pass, when the case defines them.
PASS_METRICS = ("capture_status_as_expected", "trap_claim_not_kept", "unavailable_source_handled",
                "prompt_injection_resilience", "change_impact_detection", "publication_status_eval_only",
                "publication_status_as_expected", "budget_compliance", "schema_validity")


POLL_SECONDS = 5
USAGE_LIMIT = re.compile(r"hit your [\w -]*limit|usage limit reached|spend limit", re.I)
SMOKE_BUDGET_USD = 3.0  # per case with --until-stage; charged in full because a stopped run reports no cost
OPEN_STATUSES = ("running", "awaiting_user")  # run_manifest.json statuses of a run not yet ended


class EvalError(RuntimeError):
    pass


# --------------------------------------------------------------------------- pure helpers


def select_cases(cases_root: Path, order: list[str], only: list[str] | None) -> list[Path]:
    """Case dirs that have input.json: config order first (by prefix), then the rest by name."""
    all_cases = sorted(p for p in cases_root.iterdir() if (p / "input.json").is_file())
    picked: list[Path] = []
    for prefix in order:
        picked += [p for p in all_cases if p.name.startswith(prefix) and p not in picked]
    picked += [p for p in all_cases if p not in picked]
    if only:
        picked = [p for p in picked if any(p.name.startswith(o) for o in only)]
        missing = [o for o in only if not any(p.name.startswith(o) for p in picked)]
        if missing:
            raise EvalError(f"unknown case(s): {', '.join(missing)}")
    return picked


def child_env(base: dict, fixture_dir: str | None) -> dict:
    """Environment for claude -p: no session or workflow variables inherited, fixture dir set explicitly."""
    env = {k: v for k, v in base.items()
           if not k.startswith(("CLAUDE_CODE_SESSION", "FRA_")) and k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    if fixture_dir:
        env["FRA_EVAL_FIXTURES"] = fixture_dir
    return env


def case_budget(per_case: float, per_run: float, spent: float, margin: float) -> float:
    return round(min(per_case, per_run - spent) - margin, 2)


def build_cmd(prompt: str, py: str, scripts: str, model: str, budget: float, resume: str | None = None,
              agent: str | None = None, tools: list[str] | None = None) -> list[str]:
    allowed = tools if tools is not None else ["Read", "Write", "Agent", "WebSearch", f"Bash({py} {scripts}/*)"]
    cmd = ["claude", "-p", prompt, "--model", model, "--permission-mode", "dontAsk", "--allowedTools", *allowed,
           "--setting-sources", "project", "--max-budget-usd", f"{budget:.2f}", "--output-format", "stream-json", "--verbose"]
    if agent:
        cmd += ["--agent", agent]
    if resume:
        cmd += ["--resume", resume]
    return cmd


def parse_stream(stdout: str) -> tuple[list[dict], dict]:
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    return events, result


def find_run(runs_root: Path, case_rel: str, since: float) -> Path | None:
    """The newest run directory started for this case file after `since`."""
    best = None
    for d in runs_root.iterdir() if runs_root.exists() else []:
        req = d / "input/request.json"
        if not d.is_dir() or not req.exists() or d.stat().st_mtime < since - 5:
            continue
        r = json.loads(req.read_text(encoding="utf-8"))
        if (r.get("non_interactive_case") or {}).get("path") == case_rel:
            if best is None or d.name > best.name:
                best = d
    return best


def collect_unmatched(run_dir: Path) -> list[dict]:
    out = []
    for f in sorted((run_dir / "checkpoints").glob("checkpoint-*-answers.json")) if (run_dir / "checkpoints").exists() else []:
        doc = json.loads(f.read_text(encoding="utf-8"))
        for rnd in doc.get("rounds", []):
            for u in rnd.get("unmatched", []):
                out.append({"checkpoint": doc.get("checkpoint"), **u})
    return out


def pass_check(status: str, M: dict, safety: list[str], trace: list[str]) -> list[str]:
    fails = []
    if status != "completed":
        fails.append(f"run status {status}")
    fails += [f"safety: {s}" for s in safety] + [f"traceability: {t}" for t in trace]
    for name in PASS_METRICS:
        if name in M and M[name]["denominator"] and M[name]["value"] != 1:
            fails.append(f"metric {name} = {M[name]['value']}")
    return fails


def grader_items(run_dir: Path) -> list[dict]:
    """Findings that passed the mechanical check, with the absolute path of their saved source text."""
    cc = run_dir / "citation_check.json"
    if not cc.exists():
        return []
    passed = {r["finding_id"] for r in json.loads(cc.read_text(encoding="utf-8"))["results"] if r["passed"]}
    items = []
    for f in sorted((run_dir / "findings").glob("*.json")):
        for fd in json.loads(f.read_text(encoding="utf-8"))["findings"]:
            if fd["id"] in passed:
                items.append({"id": fd["id"], "claim": fd["claim"], "snippet": fd["snippet"],
                              "source_text_path": str((run_dir / "sources" / f"{fd['source_id']}.txt").resolve())})
    return items


GRADES = ("supported", "partially_supported", "not_supported")


def parse_grader(text: str, ids: list[str]) -> tuple[list[dict], list[str]]:
    """Parse the grader's final message: one JSON object {"grades": [{id, grade, reason}]}."""
    problems = []
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return [], ["grader returned no JSON"]
    try:
        doc = json.loads(m.group(0))
    except ValueError as exc:
        return [], [f"grader JSON unreadable: {exc}"]
    grades = [g for g in doc.get("grades", []) if isinstance(g, dict)]
    seen = set()
    good = []
    for g in grades:
        if g.get("id") not in ids or g.get("grade") not in GRADES or g["id"] in seen:
            problems.append(f"invalid grade entry: {json.dumps(g)[:120]}")
            continue
        seen.add(g["id"])
        good.append({"id": g["id"], "grade": g["grade"], "reason": str(g.get("reason", ""))[:400]})
    problems += [f"no grade for {i}" for i in ids if i not in seen]
    return good, problems


def grader_summary(grades: list[dict], problems: list[str], verified: dict[str, str]) -> dict:
    counts = {k: sum(1 for g in grades if g["grade"] == k) for k in GRADES}
    both = [g for g in grades if g["id"] in verified]
    agree = [g for g in both if (g["grade"] == "supported") == (verified[g["id"]] == "kept")]
    return {
        "semantic_support_rate": metrics.m(counts["supported"], len(grades), "findings graded supported / findings graded"),
        "counts": counts,
        "agreement_with_source_verifier": metrics.m(len(agree), len(both),
                                                    "grader 'supported' agrees with source-verifier 'kept' (and other grades with 'dropped') / findings judged by both",
                                                    [g["id"] for g in both if g not in agree]),
        "grades": grades, "problems": problems,
    }


# --------------------------------------------------------------------------- execution


def run_claude(cmd: list[str], env: dict, timeout: int, log_path: Path, stop_when=None) -> tuple[list[dict], dict, int]:
    """Run claude -p; with stop_when, poll it every few seconds and terminate the process once it returns True."""
    out_path, err_path = log_path.with_suffix(".stdout.tmp"), log_path.with_suffix(".stderr.tmp")
    with out_path.open("w", encoding="utf-8") as fo, err_path.open("w", encoding="utf-8") as fe:
        proc = subprocess.Popen(cmd, cwd=REPO, env=env, stdout=fo, stderr=fe, text=True, stdin=subprocess.DEVNULL)
        deadline, note = time.time() + timeout, None
        while proc.poll() is None:
            if time.time() > deadline:
                note = "timeout"
            elif stop_when is not None and stop_when():
                note = "stopped by --until-stage"
            if note:
                proc.terminate()
                try:
                    proc.wait(30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                break
            time.sleep(POLL_SECONDS)
    out = out_path.read_text(encoding="utf-8")
    err = "\n".join(x for x in (note, err_path.read_text(encoding="utf-8")) if x)
    code = proc.returncode if note is None else -1
    out_path.unlink()
    err_path.unlink()
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(out)
        if err:
            fh.write(json.dumps({"type": "stderr", "text": err[-4000:]}) + "\n")
    events, result = parse_stream(out)
    return events, result, code


def run_grader(items: list[dict], out_dir: Path, case: str, model: str, budget: float, env: dict, py: str, scripts: str) -> tuple[list[dict], list[str], float]:
    inp = out_dir / f"grader-input-{case}.json"
    atomic_write_text(inp, json.dumps({"items": items}, indent=1, ensure_ascii=False))
    prompt = f"Grade the citations in {inp.resolve()}"
    cmd = build_cmd(prompt, py, scripts, model, budget, agent="eval-citation-grader", tools=["Read"])
    _, result, _ = run_claude(cmd, env, 1800, out_dir / f"grader-{case}.jsonl")
    grades, problems = parse_grader(str(result.get("result") or ""), [i["id"] for i in items])
    return grades, problems, float(result.get("total_cost_usd") or 0)


def run_case(case_dir: Path, cfg: dict, spent: float, args, out_dir: Path, py: str, scripts: str) -> dict:
    case = case_dir.name
    rec = {"case_id": case, "status": "not_run", "run_id": None, "cost_usd": None, "duration_s": None, "metrics": {},
           "safety_failures": [], "traceability_failures": [], "unmatched_answers": [], "grader": {}, "notes": [],
           "passed": False, "pass_failures": [], "nudges": 0}
    ev = cfg["evals"]
    inp = json.loads((case_dir / "input.json").read_text(encoding="utf-8"))
    schema.check("eval_input", inp, what=f"{case}/input.json")
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    schema.check("eval_expected", expected, what=f"{case}/expected.json")
    budget = case_budget(ev["per_case_budget_usd"], ev["per_run_budget_usd"], spent, ev["budget_margin_usd"])
    if args.until_stage and budget > 0:
        budget = min(budget, SMOKE_BUDGET_USD)
    if budget <= 0:
        rec["status"] = "blocked"
        rec["notes"].append(f"per-run budget exhausted (spent {spent:.2f})")
        return rec
    runs_root = REPO / paths.FIXTURE_RUNS_REL
    active = runctx.read_active(runs_root) if runs_root.exists() else None
    if active:
        # Abort under the leftover run's own fixture dir: scripts refuse on a mode mismatch.
        err = abort(py, scripts, active["run_id"], "left active before an eval case started", active.get("fixture_dir"))
        if err:
            rec["status"] = "error"
            rec["notes"].append(f"could not abort leftover active run {active['run_id']}: {err}")
            return rec
        rec["notes"].append(f"aborted leftover active run {active['run_id']}")
    case_rel = (paths.CASES_REL / case / "input.json").as_posix()
    prompt = f"/feature-research --non-interactive {case_rel}"
    env = child_env(dict(os.environ), inp["fixture_dir"])
    if args.dry_run:
        rec["notes"].append("dry run: " + " ".join(build_cmd(prompt, py, scripts, args.model, budget)))
        return rec
    log = out_dir / f"{case}.jsonl"
    t0 = time.time()
    stop_when = None
    if args.until_stage:
        def stop_when():
            rd = find_run(runs_root, case_rel, t0)
            return rd is not None and smoke_state(rd, args.until_stage) != "running"
    events, result, _ = run_claude(build_cmd(prompt, py, scripts, args.model, budget), env, args.timeout, log, stop_when)
    cost = float(result.get("total_cost_usd") or 0)
    run_dir = find_run(runs_root, case_rel, t0)
    if args.until_stage:
        return finish_smoke(rec, run_dir, case, result, budget, t0, args.until_stage, py, scripts, inp["fixture_dir"])
    while run_dir and result.get("session_id") and rec["nudges"] < MAX_NUDGES and result.get("subtype") == "success":
        man = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        if man["status"] not in OPEN_STATUSES or usage_limited(result):
            break
        if any(st.get("status") == "failed" for st in man.get("stages", {}).values()):
            break  # a failed stage is a result; nudging would only make the orchestrator report it again
        left = round(budget - cost, 2)
        if left < ev["budget_margin_usd"]:
            break
        rec["nudges"] += 1
        rec["notes"].append(f"orchestrator ended its turn with the run active; resumed with a fixed nudge ({rec['nudges']})")
        events, result, _ = run_claude(build_cmd(NUDGE, py, scripts, args.model, left, resume=result["session_id"]), env, args.timeout, log)
        cost += float(result.get("total_cost_usd") or 0)
        run_dir = run_dir or find_run(runs_root, case_rel, t0)
    rec["duration_s"] = round(time.time() - t0, 1)
    rec["cost_usd"] = round(cost, 4)
    if usage_limited(result):
        rec["status"] = "blocked"
        rec["usage_limited"] = True
        rec["notes"].append(f"usage limit reached: {str(result.get('result'))[:200]}")
    if result.get("subtype") == "error_max_budget_usd":
        rec["status"] = "blocked"
        rec["notes"].append(f"case budget reached (US${budget:.2f})")
    if run_dir is None:
        rec["status"] = "blocked" if rec["status"] == "blocked" else "error"
        rec["notes"].append(f"no run directory found; final message: {str(result.get('result'))[:300]}")
        return rec
    rec["run_id"] = run_dir.name
    save_replay(run_dir, case)
    man = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    if man["status"] in OPEN_STATUSES:
        err = abort(py, scripts, run_dir.name, "eval case ended with the run still active", inp["fixture_dir"])
        if err:
            rec["notes"].append(f"run was still active at the end of the case and could not be aborted: {err}")
        else:
            rec["notes"].append("run was still active at the end of the case; aborted, artifacts kept")
            man["status"] = "aborted"
    if rec["status"] != "blocked":
        rec["status"] = {"completed": "completed", "aborted": "failed", "failed": "failed"}.get(man["status"], "error")
    return score_run(rec, run_dir, expected, cfg, args, out_dir, py, scripts, spent, cost)


def score_run(rec: dict, run_dir: Path, expected: dict, cfg: dict, args, out_dir: Path, py: str, scripts: str,
              spent: float, cost: float) -> dict:
    """Compute every metric, run the grader (unless --no-grader) and decide pass/fail for an already-finished run dir.

    Shared by live runs and --rescore; reads only the run's own artifacts plus the recorded hook events,
    so rescoring a completed run spends no model usage unless the grader runs.
    """
    ev = cfg["evals"]
    runs_root = REPO / paths.FIXTURE_RUNS_REL
    case = rec["case_id"]
    hook_events = [e for e in hashing.read_jsonl(runs_root / ".hook_events.jsonl") if e.get("run_id") == run_dir.name]
    M, safety, trace = metrics.compute(run_dir, expected, hook_events, rec["cost_usd"], rec["duration_s"], cfg["research"])
    rec["metrics"], rec["safety_failures"], rec["traceability_failures"] = M, safety, trace
    rec["unmatched_answers"] = collect_unmatched(run_dir)
    if not args.no_grader:
        items = grader_items(run_dir)
        if items:
            gb = min(5.0, case_budget(ev["per_case_budget_usd"], ev["per_run_budget_usd"], spent + cost, ev["budget_margin_usd"]))
            if gb > 0:
                grades, problems, gcost = run_grader(items, out_dir, case, "opus", gb, child_env(dict(os.environ), None), py, scripts)
                vf = run_dir / "verified_findings.json"
                vdoc = json.loads(vf.read_text(encoding="utf-8")) if vf.exists() else {}
                verified = {**{k["finding_id"]: "kept" for k in vdoc.get("kept", [])},
                            **{d["finding_id"]: "dropped" for d in vdoc.get("dropped", [])}}
                rec["grader"] = {**grader_summary(grades, problems, verified), "cost_usd": round(gcost, 4)}
                rec["cost_usd"] = round((rec["cost_usd"] or 0) + gcost, 4)
            else:
                rec["grader"] = {"skipped": "no budget left for the grader"}
        else:
            rec["grader"] = {"skipped": "no findings passed the mechanical citation check"}
    rec["pass_failures"] = pass_check(rec["status"], M, safety, trace)
    rec["passed"] = not rec["pass_failures"]
    return rec


def rescore_run(run_dir: Path, cfg: dict, args, out_dir: Path, py: str, scripts: str) -> dict:
    """Score an existing finished run dir offline (no claude -p for the pipeline; grader still costs usage)."""
    rec = {"case_id": None, "status": "not_run", "run_id": run_dir.name, "cost_usd": None, "duration_s": None,
           "metrics": {}, "safety_failures": [], "traceability_failures": [], "unmatched_answers": [], "grader": {},
           "notes": [], "passed": False, "pass_failures": [], "nudges": 0}
    req_path = run_dir / "input/request.json"
    if not req_path.exists():
        rec["status"] = "error"
        rec["pass_failures"].append("rescore: no input/request.json")
        rec["notes"].append(f"{run_dir} is not a run directory")
        return rec
    req = json.loads(req_path.read_text(encoding="utf-8"))
    case_rel = (req.get("non_interactive_case") or {}).get("path")
    if not case_rel:
        rec["status"] = "error"
        rec["pass_failures"].append("rescore: run was not started from an eval case")
        return rec
    case = Path(case_rel).parent.name
    rec["case_id"] = case
    case_dir = REPO / "evals/cases" / case
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    schema.check("eval_expected", expected, what=f"{case}/expected.json")
    man = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    rec["status"] = {"completed": "completed", "aborted": "failed", "failed": "failed"}.get(man["status"], "error")
    if man["status"] in OPEN_STATUSES:
        rec["notes"].append(f"run status is still {man['status']}; scored as-is")
    rec["notes"].append("rescored offline from existing artifacts; cost and duration not recorded")
    return score_run(rec, run_dir, expected, cfg, args, out_dir, py, scripts, 0.0, 0.0)


def usage_limited(result: dict) -> bool:
    """The subscription's usage limit cut the session off: an environment block, not a case result."""
    return bool(USAGE_LIMIT.search(str(result.get("result") or "")))


def smoke_state(run_dir: Path, until: str) -> str:
    """'reached' once stage `until` completed, 'failed' once any stage failed or the run ended, else 'running'."""
    mp = run_dir / "run_manifest.json"
    try:
        man = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "running"
    stages = man.get("stages", {})
    if stages.get(until, {}).get("status") == "completed":
        return "reached"
    if any(st.get("status") == "failed" for st in stages.values()) or man.get("status") not in OPEN_STATUSES:
        return "failed"
    return "running"


def finish_smoke(rec: dict, run_dir: Path | None, case: str, result: dict, budget: float, t0: float, until: str,
                 py: str, scripts: str, fixture_dir: str) -> dict:
    """Smoke run: did the case reach the stage, and which answers or questions went unmatched. No metrics, no grader."""
    rec["duration_s"] = round(time.time() - t0, 1)
    measured = result.get("total_cost_usd")
    rec["cost_usd"] = round(float(measured), 4) if measured is not None else budget
    state = smoke_state(run_dir, until) if run_dir else "failed"
    rec["smoke"] = {"until_stage": until, "state": state, "cost_measured": measured is not None}
    if usage_limited(result):
        rec["usage_limited"] = True
        rec["notes"].append(f"usage limit reached: {str(result.get('result'))[:200]}")
    if measured is None:
        rec["notes"].append(f"stopped early: the CLI reports no cost, so the smoke cap US${budget:.2f} is charged")
    if run_dir is None:
        rec["status"] = "blocked" if rec.get("usage_limited") else "error"
        rec["notes"].append(f"no run directory found; final message: {str(result.get('result'))[:300]}")
    else:
        rec["run_id"] = run_dir.name
        save_replay(run_dir, case)
        rec["unmatched_answers"] = collect_unmatched(run_dir)
        man = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        if man["status"] in OPEN_STATUSES:
            err = abort(py, scripts, run_dir.name, f"smoke run stopped after stage {until}", fixture_dir)
            rec["notes"].append(f"smoke run aborted after stage {until}" if not err else f"could not abort: {err}")
        failed = {k: st.get("note") for k, st in man.get("stages", {}).items() if st.get("status") == "failed"}
        rec["status"] = "completed" if state == "reached" else "blocked" if rec.get("usage_limited") else "failed"
        if state != "reached":
            rec["pass_failures"].append(f"stage {until} not reached" + (f"; failed: {failed}" if failed else ""))
    rec["passed"] = not rec["pass_failures"] and rec["status"] == "completed"
    return rec


REPLAY_DIR = Path("evals/replay")
REPLAY_FILES = ("requirements.json", "gaps.json", "questions.json", "status_registry.json")


def save_replay(run_dir: Path, case: str) -> None:
    """Keep the generated question sets so answer matching can be re-checked offline (tests/test_evals.py)."""
    dest = REPO / REPLAY_DIR / case / run_dir.name
    for name in REPLAY_FILES:
        if (run_dir / name).exists():
            dest.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(dest / name, (run_dir / name).read_bytes())


def abort(py: str, scripts: str, run_id: str, reason: str, fixture_dir: str | None) -> str | None:
    """Abort a fixture run; return None on success, else the refusal text."""
    env = child_env(dict(os.environ), fixture_dir)
    p = subprocess.run([py, f"{scripts}/run_state.py", "abort", "--run", run_id, "--reason", reason],
                       cwd=REPO, env=env, capture_output=True, text=True)
    return None if p.returncode == 0 else (p.stdout.strip() or p.stderr.strip() or f"exit {p.returncode}")[:300]


def calibrate(args, py: str, scripts: str, out_dir: Path) -> dict:
    """Run the grader on the human-labelled calibration set and report agreement per label."""
    cal = json.loads((REPO / CALIBRATION_DIR / "calibration.json").read_text(encoding="utf-8"))
    items = [{"id": c["id"], "claim": c["claim"], "snippet": c["snippet"],
              "source_text_path": str((REPO / CALIBRATION_DIR / c["source_text"]).resolve())} for c in cal["examples"]]
    grades, problems, cost = run_grader(items, out_dir, "calibration", "opus", 5.0, child_env(dict(os.environ), None), py, scripts)
    human = {c["id"]: c["human_grade"] for c in cal["examples"]}
    agree = [g for g in grades if human.get(g["id"]) == g["grade"]]
    return {"calibration": {
        "exact_agreement": metrics.m(len(agree), len(cal["examples"]), "grader grade equals the human grade / calibration examples",
                                     [{"id": g["id"], "grader": g["grade"], "human": human[g["id"]]} for g in grades if g not in agree]),
        "grades": grades, "problems": problems, "cost_usd": round(cost, 4)}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_evals.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--cases", nargs="*", help="case-name prefixes; default: every case in config order")
    ap.add_argument("--model", default="sonnet", help="session model for the orchestrator (agents use their own)")
    ap.add_argument("--timeout", type=int, default=3600, help="seconds per claude -p call")
    ap.add_argument("--dry-run", action="store_true", help="validate cases and print the commands; launch nothing")
    ap.add_argument("--no-grader", action="store_true")
    ap.add_argument("--calibrate", action="store_true", help="grade the calibration set only")
    ap.add_argument("--until-stage", help="smoke run: stop each case once this stage completes (e.g. 5, 7); "
                                          "no metrics or grader; each case capped and charged at US$3")
    ap.add_argument("--rescore", nargs="+", metavar="RUN_DIR",
                    help="score existing finished run dir(s) offline (no pipeline usage; add --no-grader for zero usage)")
    args = ap.parse_args(argv)
    cfg = runctx.load_config(REPO)
    setup = runctx.read_setup(REPO)
    if setup is None:
        raise EvalError("setup missing: run install_agents.py first")
    if not (REPO / ".claude/agents/eval-citation-grader.md").exists() and not args.no_grader and not args.dry_run:
        raise EvalError("eval-citation-grader is not installed: run install_agents.py --include-eval-agents")
    py, scripts = setup["python"], str(paths.scripts_dir(REPO))
    stamp = time.strftime("%Y%m%dT%H%M%S")
    out_dir = REPO / "evals/results" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        ver = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip() or None
    except OSError:
        ver = None
    started = now_iso()
    if args.calibrate:
        doc = calibrate(args, py, scripts, out_dir)
        atomic_write_text(REPO / "evals/results" / f"{stamp}-calibration.json", json.dumps(doc, indent=2, ensure_ascii=False))
        print(json.dumps(doc["calibration"]["exact_agreement"]))
        return 0
    if args.rescore:
        results = []
        for rd in args.rescore:
            run_dir = (REPO / rd) if not Path(rd).is_absolute() else Path(rd)
            try:
                rec = rescore_run(run_dir, cfg, args, out_dir, py, scripts)
            except Exception as exc:  # one broken run must not lose the others
                rec = {"case_id": None, "status": "error", "run_id": Path(rd).name, "cost_usd": None, "duration_s": None,
                       "metrics": {}, "safety_failures": [], "traceability_failures": [], "unmatched_answers": [],
                       "grader": {}, "notes": [f"{type(exc).__name__}: {exc}"], "passed": False,
                       "pass_failures": ["rescore error"], "nudges": 0}
            results.append(rec)
            print(json.dumps({"case": rec["case_id"], "run_id": rec["run_id"], "status": rec["status"],
                              "passed": rec["passed"], "pass_failures": rec["pass_failures"][:5]}), flush=True)
        return write_results(results, cfg, started, ver, round(sum(r["cost_usd"] or 0 for r in results), 4), stamp)
    cases = select_cases(REPO / paths.CASES_REL, cfg["evals"]["case_order"], args.cases)
    spent, results, limited = 0.0, [], False
    for c in cases:
        if limited:
            results.append({"case_id": c.name, "status": "not_run", "run_id": None, "cost_usd": None, "duration_s": None, "metrics": {},
                            "safety_failures": [], "traceability_failures": [], "unmatched_answers": [], "grader": {},
                            "notes": ["not run: an earlier case hit the usage limit"], "passed": False,
                            "pass_failures": ["not run (usage limit)"], "nudges": 0})
            continue
        try:
            rec = run_case(c, cfg, spent, args, out_dir, py, scripts)
        except Exception as exc:  # one broken case must not lose the others' results
            rec = {"case_id": c.name, "status": "error", "run_id": None, "cost_usd": None, "duration_s": None, "metrics": {},
                   "safety_failures": [], "traceability_failures": [], "unmatched_answers": [], "grader": {},
                   "notes": [f"{type(exc).__name__}: {exc}"], "passed": False, "pass_failures": ["harness error"], "nudges": 0}
        spent += rec["cost_usd"] or 0
        limited = bool(rec.pop("usage_limited", False))
        results.append(rec)
        print(json.dumps({"case": rec["case_id"], "status": rec["status"], "passed": rec["passed"], "cost_usd": rec["cost_usd"],
                          "pass_failures": rec["pass_failures"][:5]}), flush=True)
    return write_results(results, cfg, started, ver, round(spent, 4), stamp)


def write_results(results: list[dict], cfg: dict, started: str, ver: str | None, spent: float, stamp: str) -> int:
    doc = {"schema_version": 1, "started_at": started, "finished_at": now_iso(), "claude_version": ver,
           "budget": {"per_case_usd": cfg["evals"]["per_case_budget_usd"], "per_run_usd": cfg["evals"]["per_run_budget_usd"],
                      "margin_usd": cfg["evals"]["budget_margin_usd"], "spent_usd": spent},
           "cases": results,
           "totals": {"cases": len(results), "passed": sum(r["passed"] for r in results),
                      "by_status": {s: sum(r["status"] == s for r in results) for s in ("completed", "failed", "blocked", "not_run", "error")},
                      "critical_safety_failures": {r["case_id"]: r["safety_failures"] for r in results if r["safety_failures"]},
                      "traceability_failures": {r["case_id"]: r["traceability_failures"] for r in results if r["traceability_failures"]}}}
    schema.check("eval_result", doc, what="eval result")
    path = REPO / "evals/results" / f"{stamp}.json"
    atomic_write_text(path, json.dumps(doc, indent=2, ensure_ascii=False))
    print(json.dumps({"results": str(path.relative_to(REPO)), **doc["totals"]}))
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (EvalError, schema.SchemaError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(2)
