#!/usr/bin/env python3
"""Run one /feature-research invocation end to end in a throwaway copy of the repository.

Usage: run_e2e.py --out DIR --prompt TEXT [--fixture evals/fixtures/<case>] [--model sonnet] [--budget 3]

The sandbox gets a copy of the repo (without .git, runs/, evals/runs/, workspaces), a
symlink to the real .venv, freshly generated agents, and project-only settings, so the
real hooks (H1, H2, H5, recorder) are active. claude -p runs with --permission-mode dontAsk
and an explicit allow list; it never skips permission checks.
"""
import argparse, json, os, shutil, subprocess, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKIP = {".git", "runs", ".venv", "feature-research-workspace", "agent-tests", "__pycache__", ".pytest_cache"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--prompt", required=True)
    ap.add_argument("--fixture"); ap.add_argument("--model", default="sonnet"); ap.add_argument("--budget", default="3")
    ap.add_argument("--continue-from", help="outputs dir of an earlier run: reuse its sandbox and session, send only the followups")
    ap.add_argument("--followups", help="JSON list of {match: regex, reply: text, max_uses: n}; after each turn the first "
                    "rule whose regex matches the orchestrator's last message (and has uses left) is sent as the "
                    "user's reply with claude -p --resume; stops when none matches or after 8 replies")
    a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    if a.continue_from:
        return continue_run(a, out)
    sb = Path(tempfile.mkdtemp(prefix="fra-e2e-"))
    def ignore(d, names):
        return [n for n in names if n in SKIP or (Path(d).name == "evals" and n == "runs")]
    shutil.copytree(REPO, sb, dirs_exist_ok=True, ignore=ignore)
    os.symlink(REPO / ".venv", sb / ".venv")
    py = str(sb / ".venv/bin/python"); scripts = str(sb / ".claude/skills/feature-research/scripts")
    inst = subprocess.run([py, f"{scripts}/install_agents.py"], cwd=sb, capture_output=True, text=True)
    (out / "install.json").write_text(inst.stdout + inst.stderr)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_CODE_SESSION", "FRA_"))}
    env.pop("CLAUDECODE", None)
    if a.fixture:
        env["FRA_EVAL_FIXTURES"] = a.fixture
    allowed = ["Read", "Write", "Agent", f"Bash({py} {scripts}/*)"]
    cmd = ["claude", "-p", a.prompt, "--model", a.model, "--permission-mode", "dontAsk",
           "--allowedTools", *allowed, "--setting-sources", "project", "--max-budget-usd", str(a.budget),
           "--output-format", "stream-json", "--verbose"]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=sb, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=1800)
    stdout_all, stderr_all = proc.stdout, proc.stderr
    events = [json.loads(l) for l in proc.stdout.splitlines() if l.strip().startswith("{")]
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    turns = [{"prompt": a.prompt, "final": result.get("result"), "cost_usd": result.get("total_cost_usd")}]
    total_cost = result.get("total_cost_usd") or 0
    import re
    rules = json.loads(a.followups) if a.followups else []
    uses = [0] * len(rules)
    for _ in range(8):
        sid = result.get("session_id")
        last = str(result.get("result") or "")
        pick = next((i for i, r in enumerate(rules) if uses[i] < r.get("max_uses", 1)
                     and re.search(r["match"], last, re.I | re.S)), None)
        ended = re.search(r"\b(aborted|stopped (after|at) stage|run (has )?ended)\b", last, re.I)
        if not sid or pick is None or ended:
            break
        uses[pick] += 1
        reply = rules[pick]["reply"]
        fcmd = list(cmd); fcmd[2] = reply; fcmd += ["--resume", sid]
        proc = subprocess.run(fcmd, cwd=sb, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=1800)
        stdout_all += proc.stdout; stderr_all += proc.stderr
        new_events = [json.loads(l) for l in proc.stdout.splitlines() if l.strip().startswith("{")]
        events += new_events
        result = next((e for e in reversed(new_events) if e.get("type") == "result"), {})
        turns.append({"prompt": reply, "final": result.get("result"), "cost_usd": result.get("total_cost_usd")})
        total_cost += result.get("total_cost_usd") or 0
    (out / "transcript.jsonl").write_text(stdout_all); (out / "stderr.txt").write_text(stderr_all)
    (out / "turns.json").write_text(json.dumps(turns, indent=2, ensure_ascii=False))
    result = {**result, "total_cost_usd": total_cost}
    calls = []
    for e in events:
        if e.get("type") == "assistant":
            for c in e["message"].get("content", []):
                if c.get("type") == "tool_use":
                    calls.append({"tool": c["name"], "input": json.dumps(c["input"])[:300],
                                  "subagent": e.get("parent_tool_use_id") is not None})
    (out / "tool_calls.json").write_text(json.dumps(calls, indent=1))
    (out / "final.md").write_text(str(result.get("result", "")))
    metrics = {"sandbox": str(sb), "duration_s": round(time.time() - t0, 1), "cost_usd": result.get("total_cost_usd"),
               "subtype": result.get("subtype"), "is_error": result.get("is_error"), "num_turns": result.get("num_turns"),
               "exit": proc.returncode, "prompt": a.prompt, "fixture": a.fixture, "model": a.model}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics))

def continue_run(a, out):
    """Resume an earlier run's sandbox and session (same transcript, same hooks), sending only the followups."""
    import re
    prev = Path(a.continue_from).resolve()
    m = json.loads((prev / "metrics.json").read_text())
    sb = Path(m["sandbox"])
    events = [json.loads(l) for l in (prev / "transcript.jsonl").read_text().splitlines() if l.strip().startswith("{")]
    result = next(e for e in reversed(events) if e.get("type") == "result")
    py = str(sb / ".venv/bin/python"); scripts = str(sb / ".claude/skills/feature-research/scripts")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_CODE_SESSION", "FRA_"))}
    env.pop("CLAUDECODE", None)
    if m.get("fixture"):
        env["FRA_EVAL_FIXTURES"] = m["fixture"]
    base = ["claude", "-p", "", "--model", m["model"], "--permission-mode", "dontAsk", "--allowedTools", "Read", "Write", "Agent",
            f"Bash({py} {scripts}/*)", "--setting-sources", "project", "--max-budget-usd", str(a.budget),
            "--output-format", "stream-json", "--verbose"]
    rules = json.loads(a.followups) if a.followups else []
    uses = [0] * len(rules)
    turns = json.loads((prev / "turns.json").read_text())
    stdout_all, total = (prev / "transcript.jsonl").read_text(), sum(t.get("cost_usd") or 0 for t in turns)
    t0 = time.time()
    first = True
    for _ in range(8):
        last = str(result.get("result") or "")
        if first and rules:
            pick, first = 0, False
        else:
            pick = next((i for i, r in enumerate(rules) if uses[i] < r.get("max_uses", 1) and re.search(r["match"], last, re.I | re.S)), None)
        if pick is None or re.search(r"\b(aborted|stopped (after|at) stage|run (has )?ended)\b", last, re.I):
            break
        uses[pick] += 1
        cmd = list(base); cmd[2] = rules[pick]["reply"]; cmd += ["--resume", result["session_id"]]
        proc = subprocess.run(cmd, cwd=sb, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=1800)
        stdout_all += proc.stdout
        evs = [json.loads(l) for l in proc.stdout.splitlines() if l.strip().startswith("{")]
        result = next((e for e in reversed(evs) if e.get("type") == "result"), {})
        turns.append({"prompt": rules[pick]["reply"], "final": result.get("result"), "cost_usd": result.get("total_cost_usd")})
        total += result.get("total_cost_usd") or 0
    (out / "transcript.jsonl").write_text(stdout_all)
    (out / "turns.json").write_text(json.dumps(turns, indent=2, ensure_ascii=False))
    (out / "final.md").write_text(str(result.get("result", "")))
    all_events = [json.loads(l) for l in stdout_all.splitlines() if l.strip().startswith("{")]
    calls = [{"tool": c["name"], "input": json.dumps(c["input"])[:300], "subagent": e.get("parent_tool_use_id") is not None}
             for e in all_events if e.get("type") == "assistant" for c in e["message"].get("content", []) if c.get("type") == "tool_use"]
    (out / "tool_calls.json").write_text(json.dumps(calls, indent=1))
    metrics = {**m, "duration_s": round(m["duration_s"] + time.time() - t0, 1), "cost_usd": total, "continued_from": str(prev)}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
