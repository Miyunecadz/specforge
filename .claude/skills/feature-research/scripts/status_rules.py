#!/usr/bin/env python3
"""status_rules.py: the only writer of status, approval, verification, staleness, issues and
decisions (BUILD_SPEC §6, §10).

Owns status_registry.json, status_history.jsonl, decisions.json, checkpoints/**,
status_labels.json and integrity/status_rules.json. Every command computes all changes in
memory and writes only if every change is valid.

  register <artifact> --run R        add an artifact's items; apply its proposed_status_changes
  decide --run R --checkpoint N --answers-b64 B64
                                     record the user's answers as DECs (H1 checks provenance first)
  decide --run R --prior             record input/prior_decisions.json at intake
  labels --run R                     derive labels, placement and gap routing -> status_labels.json
  apply / verification               Phase 6 / Phase 3

Exit codes: 0 ok, 1 invalid input or rejected change, 3 refused.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import json
import os
import sys
from pathlib import Path
from typing import Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import fsutil, hashing, modes, paths, runctx, schema, status  # noqa: E402
from _lib.runctx import RunError, now_iso  # noqa: E402

OWNER = "status_rules.py"
ARTIFACTS = {
    "requirements.json": "requirements",
    "gaps.json": "gaps",
}


def _out(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def load_state(run_dir: Path, run_id: str) -> status.State:
    reg_p, dec_p = run_dir / "status_registry.json", run_dir / "decisions.json"
    registry = (json.loads(reg_p.read_text(encoding="utf-8")) if reg_p.exists()
                else {"schema_version": 1, "run_id": run_id, "items": {}, "registered_artifacts": {}})
    decisions = (json.loads(dec_p.read_text(encoding="utf-8")) if dec_p.exists()
                 else {"schema_version": 1, "run_id": run_id, "decisions": []})
    return status.State(registry, decisions)


def save_state(run_dir: Path, st: status.State, *, decisions_changed: bool, extra: dict | None = None) -> None:
    schema.check("status_registry", st.registry, what="status_registry.json")
    schema.check("decisions", st.decisions, what="decisions.json")
    for rel, doc in (extra or {}).items():
        fsutil.atomic_write_json(run_dir / rel, doc)
        runctx.record_integrity(run_dir, OWNER, rel)
    if decisions_changed:
        fsutil.atomic_write_json(run_dir / "decisions.json", st.decisions)
        runctx.record_integrity(run_dir, OWNER, "decisions.json")
    fsutil.atomic_write_json(run_dir / "status_registry.json", st.registry)
    runctx.record_integrity(run_dir, OWNER, "status_registry.json")
    ts = now_iso()
    for c in st.changes:
        rec = {"schema_version": 1, "ts": ts, "item_id": c.item_id, "field": c.field, "old": c.old, "new": c.new,
               "reason": c.reason, "decision_id": c.decision_id, "stale_reason": c.stale_reason}
        stored = hashing.append_chained(run_dir / "status_history.jsonl", rec)
        schema.check("status_history_entry", stored, what="status_history.jsonl line")


def _load_doc(run_dir: Path, rel: str) -> dict | None:
    p = run_dir / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# --------------------------------------------------------------------------- register


def items_of(rel: str, doc: dict) -> list[dict]:
    out = []
    if rel == "requirements.json":
        out += [status.new_item(r["id"], "requirement", "customer_requirement", rel) for r in doc["requirements"]]
        out += [status.new_item(a["id"], "assumption", "assumption", rel) for a in doc["assumptions"]]
    elif rel == "gaps.json":
        out += [status.new_item(g["id"], "gap", g["provenance"], rel) for g in doc["gaps"]]
        out += [status.new_item(a["id"], "assumption", "assumption", rel) for a in doc["assumptions"]]
    return out


def cmd_register(args, ctx: runctx.RunContext) -> int:
    rel = Path(args.artifact).as_posix()
    if rel.startswith(str(ctx.run_dir)):
        rel = Path(rel).relative_to(ctx.run_dir).as_posix()
    if rel not in ARTIFACTS:
        raise RunError(f"register supports {', '.join(ARTIFACTS)} in this build; got {rel!r}")
    doc = _load_doc(ctx.run_dir, rel)
    if doc is None:
        raise RunError(f"{rel} does not exist in the run")
    schema.check(ARTIFACTS[rel], doc, what=rel)
    if doc.get("run_id") != ctx.run_id:
        raise status.StatusError(f"{rel} run_id does not match the run")
    st = load_state(ctx.run_dir, ctx.run_id)
    new = items_of(rel, doc)
    ids = [i["id"] for i in new]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise status.StatusError(f"duplicate ids inside {rel}: {', '.join(dupes)}")
    for item in new:
        status.register_item(st, item)
    for change in doc.get("proposed_status_changes", []):
        status.apply_proposed(st, change)
    if rel == "requirements.json":
        for conflict in doc.get("conflicts", []):
            for rid in conflict["ids"]:
                status.add_issue(st, rid, "conflicting", conflict["description"])
    st.registry["registered_artifacts"][rel] = hashing.sha256_file(ctx.run_dir / rel)
    save_state(ctx.run_dir, st, decisions_changed=False)
    _out({"ok": True, "artifact": rel, "items": len(new), "changes": len(st.changes)})
    return 0


# --------------------------------------------------------------------------- decide


def _agent_ids(run_dir: Path) -> tuple[list, list]:
    reqs = _load_doc(run_dir, "requirements.json") or {}
    gaps = _load_doc(run_dir, "gaps.json") or {}
    return [r["id"] for r in reqs.get("requirements", [])], [g["id"] for g in gaps.get("gaps", [])]


def decode_answers(b64: str) -> dict:
    try:
        raw = base64.b64decode(b64, validate=True)
        doc = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise status.StatusError(f"--answers-b64 is not base64-encoded UTF-8 JSON: {exc}") from exc
    return doc


def cmd_decide(args, ctx: runctx.RunContext) -> int:
    if args.prior:
        return _decide_prior(ctx)
    if not args.checkpoint or not args.answers_b64:
        raise RunError("decide needs --checkpoint and --answers-b64 (or --prior)")
    answers = decode_answers(args.answers_b64)
    schema.check("checkpoint_answers", answers, what="answers")
    cp = args.checkpoint.upper()
    if answers["checkpoint"] != cp:
        raise status.StatusError(f"answers are for checkpoint {answers['checkpoint']}, not {cp}")
    if ctx.manifest.get("open_checkpoint") != cp:
        raise RunError(f"checkpoint {cp} is not open (run 'run_state.py await-user {cp}' first)")
    if ctx.manifest.get("status") != "running":
        raise RunError("the run is still waiting for the user; run 'run_state.py continue' after they reply")
    if answers["source"] == "eval_case_file":
        req = _load_doc(ctx.run_dir, "input/request.json")
        if ctx.mode.mode != modes.FIXTURE or not req.get("non_interactive_case"):
            raise RunError("answers from an eval case file are accepted only in fixture mode with --non-interactive")
    st = load_state(ctx.run_dir, ctx.run_id)
    reqs = _load_doc(ctx.run_dir, "requirements.json") or {}
    cq_ids = {q["id"] for q in reqs.get("clarifying_questions", [])}
    for a in answers["answers"]:
        for i in a.get("affected_ids", []):
            if i.startswith("CQ-"):
                if i not in cq_ids:
                    raise status.StatusError(f"unknown clarifying question {i}")
            elif not i.startswith(("SCR-", "SRC-", "Q-", "DEC-")):
                st.item(i)
        for q in a.get("question_ids", []):
            if q.startswith("CQ-") and q not in cq_ids:
                raise status.StatusError(f"unknown clarifying question {q}")
    agent_reqs, agent_gaps = _agent_ids(ctx.run_dir)
    ts = now_iso()
    dec_ids = [status.record_decision(st, checkpoint=cp, source=answers["source"], answer=a, timestamp=ts,
                                      agent_req_ids=agent_reqs, agent_gap_ids=agent_gaps)
               for a in answers["answers"]]
    cp_rel = f"checkpoints/checkpoint-{cp}-answers.json"
    cp_doc = _load_doc(ctx.run_dir, cp_rel) or {"schema_version": 1, "checkpoint": cp, "rounds": []}
    cp_doc["rounds"].append({"at": ts, "source": answers["source"], "answers": answers["answers"], "decision_ids": dec_ids})
    schema.check("checkpoint_file", cp_doc, what=cp_rel)
    save_state(ctx.run_dir, st, decisions_changed=True, extra={cp_rel: cp_doc})
    created = [c["id"] for d in st.decisions["decisions"] if d["id"] in dec_ids for c in d["created_items"]]
    _out({"ok": True, "checkpoint": cp, "decisions": dec_ids, "created_items": created, "changes": len(st.changes)})
    return 0


def _decide_prior(ctx: runctx.RunContext) -> int:
    st1 = ctx.manifest["stages"].get("1")
    if not st1 or st1["status"] != "running":
        raise RunError("prior decisions are recorded during Stage 1 only")
    doc = _load_doc(ctx.run_dir, "input/prior_decisions.json")
    if doc is None:
        raise RunError("no input/prior_decisions.json in this run")
    schema.check("decisions", doc, what="input/prior_decisions.json")
    st = load_state(ctx.run_dir, ctx.run_id)
    if any(d["source"] == "prior_decisions_file" for d in st.decisions["decisions"]):
        raise RunError("prior decisions are already recorded")
    entries = [{"decision": d["verbatim"], "context": d.get("presented", "")} for d in doc.get("decisions", [])]
    entries += doc.get("prior", [])
    if not entries:
        raise status.StatusError("input/prior_decisions.json contains no decisions")
    ts = now_iso()
    ids = []
    for e in entries:
        ids.append(status.record_decision(st, checkpoint="prior", source="prior_decisions_file", timestamp=ts, answer={
            "presented": e.get("context") or "Prior decision supplied at intake",
            "verbatim": e["decision"],
            "interpretation": "Prior decision supplied by the user at intake; later stages apply it to matching items.",
            "affected_ids": [], "actions": []}))
    save_state(ctx.run_dir, st, decisions_changed=True)
    _out({"ok": True, "checkpoint": "prior", "decisions": ids})
    return 0


# --------------------------------------------------------------------------- labels


def cmd_labels(args, ctx: runctx.RunContext) -> int:
    st = load_state(ctx.run_dir, ctx.run_id)
    doc = {"schema_version": 1, "run_id": ctx.run_id,
           "items": {iid: status.label(item) for iid, item in sorted(st.registry["items"].items())},
           "gap_routing": status.gap_routing(st.registry, st.decisions, _load_doc(ctx.run_dir, "gaps.json"))}
    schema.check("status_labels", doc, what="status_labels.json")
    fsutil.atomic_write_json(ctx.run_dir / "status_labels.json", doc)
    runctx.record_integrity(ctx.run_dir, OWNER, "status_labels.json")
    _out({"ok": True, "items": len(doc["items"]), "gaps": len(doc["gap_routing"]),
          "research_allowed": sorted(g for g, r in doc["gap_routing"].items() if r["research_allowed"])})
    return 0


def cmd_later(phase):
    def run(args, ctx):
        raise RunError(f"'{args.command}' is implemented in {phase}")
    return run


def main(argv: Sequence[str] | None = None, repo: Path | None = None, env: Mapping[str, str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="status_rules.py")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("register")
    p.add_argument("artifact")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_register)
    p = sub.add_parser("decide")
    p.add_argument("--run", required=True)
    p.add_argument("--checkpoint")
    p.add_argument("--answers-b64")
    p.add_argument("--prior", action="store_true")
    p.set_defaults(func=cmd_decide)
    p = sub.add_parser("labels")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_labels)
    for name, phase in (("apply", "Phase 6"), ("verification", "Phase 3")):
        p = sub.add_parser(name)
        p.add_argument("rest", nargs="*")
        p.add_argument("--run", required=True)
        p.set_defaults(func=cmd_later(phase))
    args = ap.parse_args(list(sys.argv if argv is None else argv)[1:])
    repo = repo or paths.REPO_ROOT
    env = os.environ if env is None else env
    try:
        ctx = runctx.require_active_run(repo, args.run, env)
        return args.func(args, ctx)
    except RunError as exc:
        _out({"ok": False, "refused": str(exc)})
        return 3
    except (status.StatusError, schema.SchemaError) as exc:
        _out({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
