"""Shared run context for scripts: config, mode agreement, active-run and session checks.

Every script that touches a run calls require_active_run(), which refuses unless the run
is the active run for this run root, the run mode recorded in .active_run and the
manifest agrees with FRA_EVAL_FIXTURES, and (when session IDs are available) the calling
session owns the run (BUILD_SPEC §10, §16).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from . import fsutil, hashing, modes, paths

SESSION_ENV = "CLAUDE_CODE_SESSION_ID"


class RunError(RuntimeError):
    """A refusal. Scripts print it and exit with status 3."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_config(repo: Path) -> dict:
    import yaml

    from . import schema

    path = paths.skill_dir(repo) / "config.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    schema.check("config", data, what=str(path))
    return data


def read_setup(repo: Path) -> dict | None:
    path = paths.setup_path(repo)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_active(runs_root: Path) -> dict | None:
    path = runs_root / ".active_run"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def session_from_env(env: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    sid = env.get(SESSION_ENV)
    return sid or None


@dataclass
class RunContext:
    repo: Path
    mode: modes.Mode
    runs_root: Path
    run_id: str
    run_dir: Path
    active: dict | None
    manifest: dict

    def path(self, rel: str) -> Path:
        return self.run_dir / rel


def resolve_mode(repo: Path, env: Mapping[str, str] | None = None) -> modes.Mode:
    try:
        return modes.resolve_mode(repo, env)
    except modes.ModeError as exc:
        raise RunError(str(exc)) from exc


def load_run(repo: Path, run_id: str, env: Mapping[str, str] | None = None) -> RunContext:
    """Load a run without requiring it to be active (used by abort and resume)."""
    mode = resolve_mode(repo, env)
    rr = paths.runs_root(repo, mode.mode)
    run_dir = rr / run_id
    mpath = run_dir / "run_manifest.json"
    if not mpath.exists():
        raise RunError(f"no run {run_id!r} under {rr.relative_to(repo)}/")
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    if manifest.get("mode") != mode.mode:
        raise RunError(
            f"run mode mismatch: manifest says {manifest.get('mode')!r}, environment says {mode.mode!r}"
        )
    want_fixture = mode.as_record(repo)["fixture_dir"]
    if manifest.get("fixture_dir") != want_fixture:
        raise RunError("fixture directory in the manifest does not match FRA_EVAL_FIXTURES")
    return RunContext(repo, mode, rr, run_id, run_dir, read_active(rr), manifest)


def require_active_run(
    repo: Path, run_id: str, env: Mapping[str, str] | None = None
) -> RunContext:
    ctx = load_run(repo, run_id, env)
    active = ctx.active
    if active is None:
        raise RunError(f"run {run_id} is not active (no .active_run)")
    if active.get("run_id") != run_id:
        raise RunError(f"run {run_id} is not the active run (active: {active.get('run_id')})")
    if active.get("mode") != ctx.mode.mode or active.get("fixture_dir") != ctx.manifest.get("fixture_dir"):
        raise RunError("run mode mismatch between .active_run, the manifest and the environment")
    owner = active.get("session_id")
    caller = session_from_env(env)
    if owner is not None and caller != owner:
        raise RunError(
            "this run belongs to another Claude Code session; use --resume (when allowed) or --abort"
        )
    if ctx.manifest.get("status") in ("aborted", "completed"):
        raise RunError(f"run {run_id} is {ctx.manifest['status']}")
    return ctx


def record_integrity(run_dir: Path, owner: str, rel: str) -> str:
    """Record the current hash of a continuously updated file (§5, Tamper detection)."""
    stem = owner.removesuffix(".py")
    ipath = run_dir / "integrity" / f"{stem}.json"
    digest = hashing.sha256_file(run_dir / rel)
    with fsutil.file_lock(ipath):
        if ipath.exists():
            data = json.loads(ipath.read_text(encoding="utf-8"))
        else:
            data = {"schema_version": 1, "owner": owner, "files": {}}
        data["files"][rel] = {"sha256": digest, "written_at": now_iso()}
        fsutil.atomic_write_json(ipath, data)
    return digest
