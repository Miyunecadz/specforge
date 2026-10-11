#!/usr/bin/env python3
"""run_state.py: run lifecycle, manifest, audit log and tamper detection (BUILD_SPEC §10).

Owns <runs-root>/.active_run, run_manifest.json, log.jsonl, input/**, budget/active_gap.json,
warnings.json, run_summary.json and integrity/run_state.json. Reads, never writes, .heartbeat.

Subcommands: start, verify, stage, log, await-user, continue, resume, set-gap, end, abort.
Later phases add: report (Phase 5).
Exit codes: 0 ok, 1 usage/validation error, 3 refused, 4 tamper detected.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import secrets
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import attest, fsutil, hashing, modes, ownership, paths, runctx, schema, stages  # noqa: E402
from _lib.runctx import RunError, now_iso  # noqa: E402

WORKFLOW_VERSION = "0.3.0-phase3"
MAX_REQUIREMENTS_BYTES = 1_000_000
EXIT_OK, EXIT_ERROR, EXIT_REFUSED, EXIT_TAMPER = 0, 1, 3, 4


class Tamper(RuntimeError):
    def __init__(self, problems: list[dict]):
        super().__init__("tamper detected")
        self.problems = problems


# --------------------------------------------------------------------------- helpers


def _out(obj: object) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _dir_digest(files: Sequence[Path], base: Path) -> str:
    parts = [f"{p.relative_to(base).as_posix()}:{hashing.sha256_file(p)}" for p in sorted(files)]
    return hashing.sha256_text("\n".join(parts))


def _versions(repo: Path, setup: dict | None) -> dict:
    sdir = paths.skill_dir(repo)
    template = sdir / "templates" / "spec-template.md"
    skill_files = [sdir / "SKILL.md", *sorted((sdir / "references").glob("*.md"))]
    return {
        "workflow": WORKFLOW_VERSION,
        "schemas_sha256": _dir_digest(list((sdir / "schemas").glob("*.json")), sdir),
        "template_sha256": hashing.sha256_file(template) if template.exists() else None,
        "agents_src_sha256": _dir_digest(list((sdir / "agents-src").glob("*.md")), sdir),
        "skill_sha256": _dir_digest([p for p in skill_files if p.exists()], sdir),
        "claude_version": (setup or {}).get("claude_version"),
    }


def _models(repo: Path) -> dict:
    out = {}
    for f in sorted((paths.skill_dir(repo) / "agents-src").glob("*.md")):
        text = f.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        front = text.split("---", 2)[1]
        for line in front.splitlines():
            if line.startswith("model:"):
                out[f.stem] = line.split(":", 1)[1].strip()
    return out


def _log(ctx_or_dir, run_id: str, event: str, stage: str | None = None, **detail) -> dict:
    run_dir = ctx_or_dir.run_dir if hasattr(ctx_or_dir, "run_dir") else ctx_or_dir
    rec = {
        "schema_version": 1,
        "ts": now_iso(),
        "run_id": run_id,
        "event": event,
        "stage": stage,
        "detail": detail,
    }
    stored = hashing.append_chained(run_dir / "log.jsonl", rec)
    schema.check("log_event", stored, what="log event")
    return stored


def _write_manifest(run_dir: Path, manifest: dict) -> None:
    manifest["updated_at"] = now_iso()
    schema.check("run_manifest", manifest, what="run_manifest.json")
    data = fsutil.locked_atomic_write_json(run_dir / "run_manifest.json", manifest)
    _log(run_dir, manifest["run_id"], "manifest_written", sha256=hashing.sha256_bytes(data))


def _latest_manifest_hash(run_dir: Path) -> str | None:
    latest = None
    for rec in hashing.read_jsonl(run_dir / "log.jsonl"):
        if rec.get("event") == "manifest_written":
            latest = rec["detail"].get("sha256")
    return latest


def _sync_hook_events(ctx: runctx.RunContext) -> int:
    """Copy this run's new hook events into log.jsonl (§11.6). Returns number copied."""
    src = ctx.runs_root / ".hook_events.jsonl"
    events = hashing.read_jsonl(src)
    state = ctx.manifest["hook_events"]
    new = events[state["copied_lines"]:]
    copied = 0
    for ev in new:
        if ev.get("run_id") == ctx.run_id:
            _log(ctx, ctx.run_id, "hook_event", None, hook_event={k: v for k, v in ev.items() if k != "prev_hash"})
            copied += 1
    if new:
        state["copied_lines"] = len(events)
        state["last_hash"] = events[-1]["line_hash"]
        _write_manifest(ctx.run_dir, ctx.manifest)
    return copied


def _require_attestation(runs_root: Path, session_id: str | None, argv: Sequence[str]) -> None:
    hb_path = runs_root / ".heartbeat"
    if not hb_path.exists():
        raise RunError("hooks are not active: no hook attestation found (.heartbeat missing)")
    hb = json.loads(hb_path.read_text(encoding="utf-8"))
    att = hb.get("attest") or {}
    if att.get("argv_sha256") != attest.argv_digest(list(argv)):
        raise RunError("hooks are not active: no hook attestation for this exact command")
    if session_id is not None and att.get("session_id") != session_id:
        raise RunError("hook attestation came from a different session")
    age = (datetime.now(timezone.utc) - runctx.parse_iso(att["at"])).total_seconds()
    if age > attest.MAX_AGE_SECONDS or age < -5:
        raise RunError("hook attestation is stale")


def _decode_requirements(args) -> tuple[bytes, str, str | None]:
    if args.requirements_b64 is not None:
        try:
            data = base64.b64decode(args.requirements_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RunError(f"--requirements-b64 is not valid base64: {exc}") from exc
        source, original = "text", None
    else:
        p = Path(args.requirements_file).expanduser()
        if not p.is_file():
            raise RunError(f"requirements file not found: {args.requirements_file}")
        if p.stat().st_size > MAX_REQUIREMENTS_BYTES:
            raise RunError("requirements file is larger than 1 MB")
        data = p.read_bytes()
        source, original = "file", str(p.resolve())
    if not data.strip():
        raise RunError("requirements are empty")
    if len(data) > MAX_REQUIREMENTS_BYTES:
        raise RunError("requirements are larger than 1 MB")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RunError("requirements must be UTF-8 text") from exc
    return data, source, original


def _declared_type(url: str) -> str:
    low = url.lower().split("?", 1)[0]
    if "figma.com/" in low or low.endswith(".figma.json"):
        return "figma"
    if low.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return "image"
    if low.startswith(("http://", "https://", "file://", "/")) or low.endswith((".html", ".htm")):
        return "html"
    return "unknown"


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


# --------------------------------------------------------------------------- verify


def verify_run(ctx: runctx.RunContext) -> list[dict]:
    """Re-check every recorded hash and hash chain. Returns tamper problems."""
    problems: list[dict] = []
    run_dir, m = ctx.run_dir, ctx.manifest

    def problem(rel: str, what: str, last_writer: str | None = None, root: bool = False):
        cls = ownership.classify(ctx.runs_root, (ctx.runs_root if root else run_dir) / rel)
        problems.append(
            {"file": rel if root else f"{ctx.run_id}/{rel}", "owner": cls.owner or "nobody (unowned path)",
             "last_writer": last_writer, "problem": what}
        )

    # Manifest: its latest hash is recorded in the hash-chained log.
    recorded = _latest_manifest_hash(run_dir)
    actual = hashing.sha256_file(run_dir / "run_manifest.json")
    if recorded != actual:
        problem("run_manifest.json", "content does not match the hash recorded in log.jsonl", "run_state.py")

    # .active_run, when it refers to this run.
    active_path = ctx.runs_root / ".active_run"
    if ctx.active and ctx.active.get("run_id") == ctx.run_id:
        if m.get("active_run_sha256") != hashing.sha256_file(active_path):
            problem(".active_run", "content does not match the hash in run_manifest.json", "run_state.py", root=True)

    # Hash chains.
    for rel in ("log.jsonl", "status_history.jsonl", "fetch_log.jsonl", "budget/searches.jsonl"):
        for p in hashing.verify_chain(run_dir / rel):
            problem(rel, f"broken hash chain: {p}")
    for p in hashing.verify_chain(ctx.runs_root / ".hook_events.jsonl"):
        problem(".hook_events.jsonl", f"broken hash chain: {p}", "hooks", root=True)

    # Stage outputs.
    recorded_files: set[str] = set()
    for key, st in m["stages"].items():
        if st["status"] != "completed":
            recorded_files.update(st["outputs"])
            continue
        for rel, digest in st["outputs"].items():
            recorded_files.add(rel)
            p = run_dir / rel
            if not p.is_file():
                problem(rel, "stage output is missing", f"stage {key}")
            elif hashing.sha256_file(p) != digest:
                problem(rel, "stage output changed after the stage completed", f"stage {key}")
        stage = stages.STAGES.get(key)
        if stage:
            found, _ = stages.expand_outputs(run_dir, stage)
            for rel in found:
                if rel not in st["outputs"]:
                    problem(rel, "file appeared in a completed stage's output area", f"stage {key}")

    # Continuously updated script files.
    for ipath in sorted((run_dir / "integrity").glob("*.json")):
        data = json.loads(ipath.read_text(encoding="utf-8"))
        for rel, info in data.get("files", {}).items():
            p = run_dir / rel
            if not p.is_file() or hashing.sha256_file(p) != info["sha256"]:
                problem(rel, "content does not match the hash its owning script recorded", data.get("owner"))

    # Files nobody may write.
    for p in sorted(run_dir.rglob("*")):
        if not p.is_file() or stages._transient(p):
            continue
        rel = p.relative_to(run_dir).as_posix()
        owner, kind = ownership.owner_of_run_path(rel)
        if kind == ownership.UNOWNED:
            problem(rel, "file is not in the ownership table, so no one may write it")
    return problems


def _verify_or_raise(ctx: runctx.RunContext) -> None:
    _sync_hook_events(ctx)
    problems = verify_run(ctx)
    if problems:
        _log(ctx, ctx.run_id, "tamper_report", None, problems=problems)
        raise Tamper(problems)
    _log(ctx, ctx.run_id, "verify_passed", None)


# --------------------------------------------------------------------------- commands


def cmd_start(args, repo: Path, env: Mapping[str, str], argv: Sequence[str]) -> int:
    mode = runctx.resolve_mode(repo, env)
    runctx.load_config(repo)
    setup = runctx.read_setup(repo)
    if setup is None:
        raise RunError("setup missing: run install_agents.py before starting a run")
    if os.path.abspath(sys.executable) != setup["python"]:
        raise RunError(f"run_state.py must run under the recorded interpreter {setup['python']}")
    if args.non_interactive and mode.mode != modes.FIXTURE:
        raise RunError("--non-interactive is refused unless eval fixture mode is validly active")
    case_rec = None
    if args.non_interactive:
        case = Path(args.non_interactive)
        case = (case if case.is_absolute() else repo / case).resolve()
        cases_root = (repo / paths.CASES_REL).resolve()
        if cases_root not in case.parents or not case.is_file():
            raise RunError("--non-interactive answer file must be a file inside evals/cases/")
        case_rec = {"path": case.relative_to(repo.resolve()).as_posix(), "sha256": hashing.sha256_file(case)}

    session_id = runctx.session_from_env(env)
    if setup.get("session_ids", True) and session_id is None:
        raise RunError(f"{runctx.SESSION_ENV} is not set; cannot bind the run to a session")
    rr = paths.runs_root(repo, mode.mode)
    rr.mkdir(parents=True, exist_ok=True)
    _require_attestation(rr, session_id, argv)
    if (rr / ".active_run").exists():
        other = runctx.read_active(rr) or {}
        raise RunError(
            f"another run is active ({other.get('run_id')}); finish it, or use --abort {other.get('run_id')}"
        )

    data, source, original = _decode_requirements(args)
    run_id = _new_run_id()
    run_dir = rr / run_id
    run_dir.mkdir(parents=False, exist_ok=False)
    started = now_iso()
    fixture_rel = mode.as_record(repo)["fixture_dir"]

    fsutil.atomic_write_bytes(run_dir / "input" / "requirements.md", data)
    prior = None
    if args.prior_decisions:
        pd = Path(args.prior_decisions).expanduser()
        try:
            pdoc = json.loads(pd.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RunError(f"prior decisions file is not readable JSON: {exc}") from exc
        errs = schema.errors("decisions", pdoc)
        if errs:
            raise RunError("prior decisions file does not match schemas/decisions.schema.json: " + "; ".join(errs[:5]))
        shutil.copyfile(pd, run_dir / "input" / "prior_decisions.json")
        prior = {"original_path": str(pd.resolve()), "copy_path": "input/prior_decisions.json",
                 "sha256": hashing.sha256_file(run_dir / "input" / "prior_decisions.json")}
    config_src = paths.skill_dir(repo) / "config.yaml"
    shutil.copyfile(config_src, run_dir / "input" / "config.yaml")

    request = {
        "schema_version": 1, "run_id": run_id, "mode": mode.mode, "fixture_dir": fixture_rel,
        "started_at": started, "mockup_url": args.mockup_url,
        "declared_input_type": _declared_type(args.mockup_url),
        "requirements": {"source": source, "original_path": original, "copy_path": "input/requirements.md",
                         "sha256": hashing.sha256_bytes(data), "bytes": len(data)},
        "prior_decisions": prior, "non_interactive_case": case_rec,
    }
    schema.check("request", request, what="input/request.json")
    fsutil.atomic_write_json(run_dir / "input" / "request.json", request)

    active = {"schema_version": 1, "run_id": run_id, "mode": mode.mode, "fixture_dir": fixture_rel,
              "session_id": session_id, "started_at": started, "resumed_at": None}
    schema.check("active_run", active, what=".active_run")
    _log(run_dir, run_id, "run_started", "1", mode=mode.mode, fixture_dir=fixture_rel,
         mockup_url=args.mockup_url, requirements_source=source, session_id=session_id)

    hook_events = hashing.read_jsonl(rr / ".hook_events.jsonl")
    manifest = {
        "schema_version": 1, "run_id": run_id, "mode": mode.mode, "fixture_dir": fixture_rel,
        "status": "running", "created_at": started, "updated_at": started, "session_id": session_id,
        "versions": _versions(repo, setup), "models": _models(repo),
        "config_sha256": hashing.sha256_file(config_src), "current_stage": "1",
        "awaiting_checkpoint": None, "open_checkpoint": None,
        "stages": {"1": {"status": "running", "started_at": started, "completed_at": None,
                         "attempts": 1, "outputs": {}, "note": None}},
        "active_run_sha256": None,
        "hook_events": {"copied_lines": len(hook_events),
                        "last_hash": hook_events[-1]["line_hash"] if hook_events else hashing.GENESIS},
        "abort_reason": None, "publication_status": "eval_only" if mode.mode == modes.FIXTURE else None,
        "dependencies": {"capture/**": ["input/request.json"], "inventory.json": ["capture/**"]},
    }
    active_bytes = fsutil.dumps_json(active).encode("utf-8")
    manifest["active_run_sha256"] = hashing.sha256_bytes(active_bytes)
    _write_manifest(run_dir, manifest)
    try:
        fd = os.open(rr / ".active_run", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as exc:
        raise RunError("another run became active while starting") from exc
    with os.fdopen(fd, "wb") as fh:
        fh.write(active_bytes)
        fh.flush()
        os.fsync(fh.fileno())
    _out({"ok": True, "run_id": run_id, "run_dir": str(run_dir.relative_to(repo)), "mode": mode.mode,
          "declared_input_type": request["declared_input_type"], "next": "stage 1: run check_url.py, then stage 1 --complete"})
    return EXIT_OK


def cmd_verify(args, repo: Path, env: Mapping[str, str], argv) -> int:
    ctx = runctx.require_active_run(repo, args.run, env)
    try:
        _verify_or_raise(ctx)
    except Tamper as t:
        _out({"ok": False, "tamper": t.problems})
        return EXIT_TAMPER
    _out({"ok": True, "run_id": ctx.run_id})
    return EXIT_OK


def _prior_stages_done(manifest: dict, key: str) -> list[str]:
    missing = []
    for k in stages.ORDER[: stages.ORDER.index(key)]:
        st = manifest["stages"].get(k)
        if k in stages.OPTIONAL_STAGES and st is None:
            continue
        if not st or st["status"] not in ("completed", "skipped"):
            missing.append(k)
    return missing


def cmd_stage(args, repo: Path, env: Mapping[str, str], argv) -> int:
    ctx = runctx.require_active_run(repo, args.run, env)
    key = args.n.upper()
    stage = stages.STAGES.get(key)
    if stage is None:
        raise RunError(f"unknown stage {args.n!r}")
    if not stage.available:
        raise RunError(f"stage {key} ({stage.name}) is not implemented in this build phase")
    m = ctx.manifest
    try:
        _verify_or_raise(ctx)
    except Tamper as t:
        _out({"ok": False, "tamper": t.problems})
        return EXIT_TAMPER
    st = m["stages"].get(key)
    now = now_iso()

    if args.action == "start":
        missing = _prior_stages_done(m, key)
        if missing:
            raise RunError(f"cannot start stage {key}: earlier stages not complete: {', '.join(missing)}")
        if st and st["status"] == "running":
            raise RunError(f"stage {key} is already running (stage 1 is started by run_state.py start)")
        if st and st["status"] == "completed":
            raise RunError(f"stage {key} is already completed")
        if any(m["stages"].get(k, {}).get("status") == "running" for k in m["stages"] if k != key):
            raise RunError("another stage is still running; complete or fail it first")
        attempts = (st["attempts"] + 1) if st else 1
        m["stages"][key] = {"status": "running", "started_at": now, "completed_at": None,
                            "attempts": attempts, "outputs": {}, "note": None}
        m["current_stage"] = key
        if attempts > 1:
            _log(ctx, ctx.run_id, "stage_retry", key, attempt=attempts)
        _log(ctx, ctx.run_id, "stage_started", key, name=stage.name, attempt=attempts)
        _write_manifest(ctx.run_dir, m)
        _out({"ok": True, "stage": key, "status": "running", "attempt": attempts})
        return EXIT_OK

    if not st or st["status"] != "running":
        raise RunError(f"stage {key} is not running")

    if args.action == "skip":
        why_not = stages.skip_allowed(ctx.run_dir, key)
        if why_not:
            raise RunError(f"stage {key} cannot be skipped: {why_not}")
        st.update(status="skipped", completed_at=now, note=args.reason)
        _log(ctx, ctx.run_id, "stage_completed", key, skipped=True, reason=args.reason)
        _write_manifest(ctx.run_dir, m)
        _out({"ok": True, "stage": key, "status": "skipped"})
        return EXIT_OK

    if args.action == "fail":
        st.update(status="failed", completed_at=now, note=args.reason)
        _log(ctx, ctx.run_id, "stage_failed", key, reason=args.reason)
        _write_manifest(ctx.run_dir, m)
        _out({"ok": True, "stage": key, "status": "failed"})
        return EXIT_OK

    # complete
    found, missing = stages.expand_outputs(ctx.run_dir, stage)
    errors: list[str] = [f"missing output: {p}" for p in missing]
    for rel, schema_name in stage.schemas.items():
        p = ctx.run_dir / rel
        if not p.exists():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as exc:
            errors.append(f"{rel}: not valid JSON: {exc}")
            continue
        errors += [f"{rel}{e}" for e in schema.errors(schema_name, doc)]
    if not errors:
        errors += stages.semantic_checks(ctx.run_dir, stage, m)
    if stage.kind in ("agent", "mixed") and stage.agent and not errors and (found or key != "8"):
        if not _subagent_seen(ctx, stage.agent, st["started_at"]):
            errors.append(
                f"no {stage.agent} subagent invocation was recorded in .hook_events.jsonl after stage "
                f"{key} started; agent outputs must be written by that subagent"
            )
    if errors:
        _log(ctx, ctx.run_id, "validation_failed", key, errors=errors[:100])
        _out({"ok": False, "stage": key, "errors": errors})
        return EXIT_ERROR
    st.update(status="completed", completed_at=now, outputs={rel: hashing.sha256_file(p) for rel, p in found.items()})
    if stage.kind == "checkpoint":
        m["open_checkpoint"] = None
    _log(ctx, ctx.run_id, "stage_completed", key, outputs=st["outputs"], attempts=st["attempts"])
    _write_manifest(ctx.run_dir, m)
    _out({"ok": True, "stage": key, "status": "completed", "outputs": sorted(st["outputs"])})
    return EXIT_OK


def _subagent_seen(ctx: runctx.RunContext, agent: str, since: str) -> bool:
    since_dt = runctx.parse_iso(since)
    names = ownership.RESEARCHER_VARIANTS if agent == "web-researcher" else (agent,)
    for ev in hashing.read_jsonl(ctx.runs_root / ".hook_events.jsonl"):
        if (ev.get("event") == "subagent_start" and ev.get("run_id") == ctx.run_id
                and ev.get("agent_type") in names and runctx.parse_iso(ev["ts"]) >= since_dt):
            return True
    return False


def cmd_await_user(args, repo: Path, env: Mapping[str, str], argv) -> int:
    ctx = runctx.require_active_run(repo, args.run, env)
    cp = args.checkpoint.upper()
    key = stages.STAGE_OF_CHECKPOINT.get(cp)
    if key is None:
        raise RunError(f"unknown checkpoint {args.checkpoint!r} (expected 1, 2, 3 or 13R)")
    m = ctx.manifest
    st = m["stages"].get(key)
    if not st or st["status"] != "running":
        raise RunError(f"stage {key} (checkpoint {cp}) is not running; start it first")
    try:
        _verify_or_raise(ctx)
    except Tamper as t:
        _out({"ok": False, "tamper": t.problems})
        return EXIT_TAMPER
    m.update(status="awaiting_user", awaiting_checkpoint=cp, open_checkpoint=cp)
    _log(ctx, ctx.run_id, "await_user", key, checkpoint=cp)
    _write_manifest(ctx.run_dir, m)
    _out({"ok": True, "checkpoint": cp, "status": "awaiting_user",
          "next": "present the checkpoint and end your turn"})
    return EXIT_OK


def cmd_continue(args, repo: Path, env: Mapping[str, str], argv) -> int:
    ctx = runctx.require_active_run(repo, args.run, env)
    _require_attestation(ctx.runs_root, runctx.session_from_env(env), argv)
    m = ctx.manifest
    if m["status"] != "awaiting_user":
        raise RunError(f"run is {m['status']}, not waiting for the user")
    try:
        _verify_or_raise(ctx)
    except Tamper as t:
        _out({"ok": False, "tamper": t.problems})
        return EXIT_TAMPER
    cp = m["awaiting_checkpoint"]
    m.update(status="running", awaiting_checkpoint=None)
    _log(ctx, ctx.run_id, "continued", stages.STAGE_OF_CHECKPOINT.get(cp), checkpoint=cp)
    _write_manifest(ctx.run_dir, m)
    _out({"ok": True, "checkpoint": cp, "status": "running",
          "next": f"record the answers with status_rules.py decide --checkpoint {cp}"})
    return EXIT_OK


def _owner_heartbeat_expired(ctx: runctx.RunContext, repo: Path) -> bool:
    hb_path = ctx.runs_root / ".heartbeat"
    owner = (ctx.active or {}).get("session_id")
    timeout = runctx.load_config(repo)["run"]["active_run_timeout_minutes"]
    if not hb_path.exists():
        return True
    hb = json.loads(hb_path.read_text(encoding="utf-8"))
    stamps = [runctx.parse_iso(v["updated_at"]) for k, v in hb.get("sessions", {}).items() if owner is None or k == owner]
    if not stamps:
        return True
    age_min = (datetime.now(timezone.utc) - max(stamps)).total_seconds() / 60
    return age_min > timeout


def cmd_resume(args, repo: Path, env: Mapping[str, str], argv) -> int:
    """Take over a run that is waiting at a checkpoint or whose owner's heartbeat expired (§4, Resume)."""
    ctx = runctx.load_run(repo, args.run, env)
    m = ctx.manifest
    if m["status"] in ("aborted", "completed"):
        raise RunError(f"run {ctx.run_id} is {m['status']} and cannot be resumed")
    if ctx.active and ctx.active.get("run_id") != ctx.run_id:
        raise RunError(f"another run is active ({ctx.active.get('run_id')})")
    session_id = runctx.session_from_env(env)
    _require_attestation(ctx.runs_root, session_id, argv)
    same_session = ctx.active and ctx.active.get("session_id") == session_id
    if not same_session and m["status"] != "awaiting_user" and not _owner_heartbeat_expired(ctx, repo):
        raise RunError("another session may still be working on this run (heartbeat is fresh and the run is not "
                       "waiting at a checkpoint); use --abort first if it is stuck")
    try:
        _sync_hook_events(ctx)
        problems = verify_run(ctx)
    except (OSError, ValueError) as exc:
        problems = [{"file": "?", "owner": "?", "last_writer": None, "problem": f"cannot verify: {exc}"}]
    if problems:
        _log(ctx, ctx.run_id, "tamper_report", None, problems=problems)
        _out({"ok": False, "tamper": problems})
        return EXIT_TAMPER
    # Re-validate completed outputs against today's schemas; invalid ones make their stage and later ones stale.
    stale_from = None
    for key in stages.ORDER:
        st = m["stages"].get(key)
        stage = stages.STAGES[key]
        if not st or st["status"] != "completed" or stale_from:
            if stale_from and st and st["status"] == "completed":
                st.update(status="stale", note=f"stale: earlier stage {stale_from} is stale")
            continue
        errs = []
        for rel, sname in stage.schemas.items():
            p = ctx.run_dir / rel
            if p.exists():
                errs += schema.errors(sname, json.loads(p.read_text(encoding="utf-8")))
        if errs:
            st.update(status="stale", note="stale: output no longer matches its schema: " + errs[0])
            stale_from = key
    now = now_iso()
    active = {"schema_version": 1, "run_id": ctx.run_id, "mode": ctx.mode.mode, "fixture_dir": m["fixture_dir"],
              "session_id": session_id, "started_at": m["created_at"], "resumed_at": now}
    data = fsutil.dumps_json(active).encode("utf-8")
    m["active_run_sha256"] = hashing.sha256_bytes(data)
    m["session_id"] = session_id
    nxt = next((k for k in stages.ORDER if k not in stages.OPTIONAL_STAGES
                and m["stages"].get(k, {}).get("status") != "completed"), None)
    _log(ctx, ctx.run_id, "run_resumed", nxt, session_id=session_id, previous_session=(ctx.active or {}).get("session_id"),
         stale_from=stale_from)
    _write_manifest(ctx.run_dir, m)
    fsutil.atomic_write_bytes(ctx.runs_root / ".active_run", data)
    rounds = []
    if m.get("open_checkpoint"):
        p = ctx.run_dir / f"checkpoints/checkpoint-{m['open_checkpoint']}-answers.json"
        if p.exists():
            rounds = json.loads(p.read_text(encoding="utf-8"))["rounds"]
    _out({"ok": True, "run_id": ctx.run_id, "status": m["status"], "next_stage": nxt,
          "open_checkpoint": m.get("open_checkpoint"), "recorded_answer_rounds": len(rounds),
          "stale_from": stale_from})
    return EXIT_OK


def cmd_set_gap(args, repo: Path, env: Mapping[str, str], argv) -> int:
    """Record the gap being researched, with budget limits for hook H3 (§11.4). Research runs one gap at a time."""
    ctx = runctx.require_active_run(repo, args.run, env)
    st = ctx.manifest["stages"].get("8")
    if not st or st["status"] != "running":
        raise RunError("set-gap is used only while stage 8 (research) is running")
    gap = None
    if not args.clear:
        gap = args.gap
        labels_p = ctx.run_dir / "status_labels.json"
        routing = json.loads(labels_p.read_text(encoding="utf-8"))["gap_routing"] if labels_p.exists() else {}
        if not routing.get(gap, {}).get("research_allowed"):
            raise RunError(f"{gap} is not approved for research (status_rules.py labels shows research_allowed=false)")
    cfg = runctx.load_config(repo)
    res = cfg["research"]
    doc = {"schema_version": 1, "kind": "active_gap", "run_id": ctx.run_id, "gap_id": gap, "set_at": now_iso(),
           "limits": {"searches_per_gap": res["searches_per_gap"], "fetches_per_gap": res["fetches_per_gap"],
                      "findings_per_gap": res["findings_per_gap"], "total_searches_per_run": res["total_searches_per_run"],
                      "allow_domains": cfg["sources"]["allow_domains"], "deny_domains": cfg["sources"]["deny_domains"]}}
    schema.check("budget", doc, what="budget/active_gap.json")
    fsutil.locked_atomic_write_json(ctx.run_dir / "budget/active_gap.json", doc)
    runctx.record_integrity(ctx.run_dir, "run_state.py", "budget/active_gap.json")
    _log(ctx, ctx.run_id, "note", "8", message=f"active gap set to {gap}")
    _out({"ok": True, "gap_id": gap, "limits": doc["limits"]})
    return EXIT_OK


def cmd_log(args, repo: Path, env, argv) -> int:
    ctx = runctx.require_active_run(repo, args.run, env)
    _log(ctx, ctx.run_id, "note", args.stage, message=args.message)
    _out({"ok": True})
    return EXIT_OK


def _remove_active_if(ctx: runctx.RunContext) -> bool:
    path = ctx.runs_root / ".active_run"
    active = runctx.read_active(ctx.runs_root)
    if active and active.get("run_id") == ctx.run_id:
        path.unlink()
        return True
    return False


def cmd_end(args, repo: Path, env, argv) -> int:
    ctx = runctx.require_active_run(repo, args.run, env)
    try:
        _verify_or_raise(ctx)
    except Tamper as t:
        _out({"ok": False, "tamper": t.problems})
        return EXIT_TAMPER
    m = ctx.manifest
    m["status"] = "completed"
    m["active_run_sha256"] = None
    _log(ctx, ctx.run_id, "run_ended", None, publication_status=m.get("publication_status"))
    _write_manifest(ctx.run_dir, m)
    _remove_active_if(ctx)
    _out({"ok": True, "run_id": ctx.run_id, "status": "completed"})
    return EXIT_OK


def cmd_abort(args, repo: Path, env, argv) -> int:
    """Abort is allowed from any session: its purpose is clearing a stuck run (§4, §11.3)."""
    ctx = runctx.load_run(repo, args.run, env)
    m = ctx.manifest
    if m["status"] == "aborted":
        raise RunError(f"run {ctx.run_id} is already aborted")
    if m["status"] == "completed":
        raise RunError(f"run {ctx.run_id} is completed and cannot be aborted")
    m["status"] = "aborted"
    m["abort_reason"] = args.reason
    m["active_run_sha256"] = None
    _log(ctx, ctx.run_id, "run_aborted", m.get("current_stage"), reason=args.reason,
         by_session=runctx.session_from_env(env))
    _write_manifest(ctx.run_dir, m)
    removed = _remove_active_if(ctx)
    _out({"ok": True, "run_id": ctx.run_id, "status": "aborted", "active_run_removed": removed,
          "artifacts_preserved": True})
    return EXIT_OK


def cmd_later(phase: str):
    def run(args, repo, env, argv) -> int:
        raise RunError(f"'{args.command}' is implemented in {phase}")
    return run


# --------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="run_state.py", description="Feature research run state")
    sub = ap.add_subparsers(dest="command", required=True)

    s = sub.add_parser("start")
    s.add_argument("--mockup-url", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--requirements-b64", help="requirements text as base64-encoded UTF-8")
    g.add_argument("--requirements-file")
    s.add_argument("--prior-decisions")
    s.add_argument("--non-interactive", metavar="CASE_FILE")
    s.set_defaults(func=cmd_start)

    for name, func in (("verify", cmd_verify), ("end", cmd_end)):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
        p.set_defaults(func=func)

    p = sub.add_parser("abort")
    p.add_argument("--run", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_abort)

    p = sub.add_parser("stage")
    p.add_argument("n")
    p.add_argument("--run", required=True)
    act = p.add_mutually_exclusive_group(required=True)
    act.add_argument("--start", dest="action", action="store_const", const="start")
    act.add_argument("--complete", dest="action", action="store_const", const="complete")
    act.add_argument("--fail", dest="action", action="store_const", const="fail")
    act.add_argument("--skip", dest="action", action="store_const", const="skip")
    p.add_argument("--reason")
    p.set_defaults(func=cmd_stage)

    p = sub.add_parser("log")
    p.add_argument("--run", required=True)
    p.add_argument("--message", required=True)
    p.add_argument("--stage")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("await-user")
    p.add_argument("checkpoint")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_await_user)
    for name, func in (("continue", cmd_continue), ("resume", cmd_resume)):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
        p.set_defaults(func=func)

    p = sub.add_parser("set-gap")
    p.add_argument("gap", nargs="?")
    p.add_argument("--run", required=True)
    p.add_argument("--clear", action="store_true")
    p.set_defaults(func=cmd_set_gap)

    for name, phase in (("report", "Phase 5"),):
        p = sub.add_parser(name)
        p.add_argument("rest", nargs="*")
        p.add_argument("--run")
        p.set_defaults(func=cmd_later(phase))
    return ap


def main(argv: Sequence[str] | None = None, repo: Path | None = None,
         env: Mapping[str, str] | None = None) -> int:
    full_argv = list(sys.argv if argv is None else argv)
    repo = repo or paths.REPO_ROOT
    env = os.environ if env is None else env
    args = build_parser().parse_args(full_argv[1:])
    if args.command == "stage" and args.action in ("fail", "skip") and not args.reason:
        print(f"stage --{args.action} requires --reason", file=sys.stderr)
        return EXIT_ERROR
    try:
        return args.func(args, repo, env, full_argv)
    except RunError as exc:
        _out({"ok": False, "refused": str(exc)})
        return EXIT_REFUSED
    except schema.SchemaError as exc:
        _out({"ok": False, "error": str(exc)})
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
