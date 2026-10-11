"""Shared hook helper (BUILD_SPEC §11.3): active-run lookup, heartbeat, hash-chained events.

This is the only code that writes <runs-root>/.heartbeat and <runs-root>/.hook_events.jsonl.
Stdlib only: hooks run under the system python3, not the project virtual environment.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOOKS_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / ".claude/skills/feature-research/scripts"))

from _lib import fsutil, hashing, modes, paths  # noqa: E402

WORKFLOW_AGENTS_BASE = (
    "mockup-extractor",
    "requirements-parser",
    "gap-analyst",
    "source-verifier",
    "feasibility-analyst",
    "question-generator",
    "doc-writer",
    "doc-reviewer",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@dataclass
class HookContext:
    repo: Path
    env: dict
    payload: dict
    runs_root: Path
    setup: dict | None
    active: dict | None  # the active run, only when it applies to this session

    @property
    def session_id(self) -> str | None:
        return self.payload.get("session_id") or None

    @property
    def agent_type(self) -> str | None:
        """Set by Claude Code for calls made inside a subagent; absent for the main session."""
        return self.payload.get("agent_type") or None

    @property
    def run_id(self) -> str | None:
        return self.active.get("run_id") if self.active else None


def read_setup(repo: Path) -> dict | None:
    p = paths.setup_path(repo)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _timeout_minutes(repo: Path) -> int:
    text = (paths.skill_dir(repo) / "config.yaml").read_text(encoding="utf-8")
    m = re.search(r"^\s*active_run_timeout_minutes:\s*(\d+)", text, re.M)
    return int(m.group(1)) if m else 120


def read_heartbeat(runs_root: Path) -> dict:
    p = runs_root / ".heartbeat"
    if not p.exists():
        return {"schema_version": 1, "sessions": {}, "attest": None}
    return json.loads(p.read_text(encoding="utf-8"))


def active_for_session(repo: Path, runs_root: Path, payload: dict) -> dict | None:
    """Return the active run if it governs this session (§11.3, The active run)."""
    p = runs_root / ".active_run"
    if not p.exists():
        return None
    active = json.loads(p.read_text(encoding="utf-8"))
    sid = payload.get("session_id")
    if sid and active.get("session_id"):
        return active if active["session_id"] == sid else None
    # Session IDs unavailable: every session is restricted until the heartbeat expires.
    hb = read_heartbeat(runs_root)
    stamps = [parse_iso(s["updated_at"]) for s in hb.get("sessions", {}).values()]
    last = max(stamps) if stamps else parse_iso(active["started_at"])
    age_min = (datetime.now(timezone.utc) - last).total_seconds() / 60
    return active if age_min <= _timeout_minutes(repo) else None


def build_context(payload: dict, env: dict, repo: Path = REPO_ROOT) -> HookContext:
    runs_root = modes.hook_runs_root(repo, env)
    return HookContext(
        repo=repo,
        env=env,
        payload=payload,
        runs_root=runs_root,
        setup=read_setup(repo),
        active=active_for_session(repo, runs_root, payload),
    )


def any_active_run(repo: Path) -> bool:
    return any((paths.runs_root(repo, m) / ".active_run").exists() for m in (modes.NORMAL, modes.FIXTURE))


def touch_heartbeat(runs_root: Path, session_id: str | None, tool: str, attest: dict | None = None) -> None:
    path = runs_root / ".heartbeat"
    runs_root.mkdir(parents=True, exist_ok=True)
    with fsutil.file_lock(path):
        hb = read_heartbeat(runs_root)
        hb.setdefault("sessions", {})[session_id or "unknown"] = {"updated_at": now_iso(), "last_tool": tool}
        if attest is not None:
            hb["attest"] = attest
        fsutil.atomic_write_json(path, hb)


def record_event(
    ctx: HookContext,
    event: str,
    hook: str,
    reason: str | None = None,
    detail: dict | None = None,
) -> None:
    ctx.runs_root.mkdir(parents=True, exist_ok=True)
    hashing.append_chained(
        ctx.runs_root / ".hook_events.jsonl",
        {
            "schema_version": 1,
            "ts": now_iso(),
            "event": event,
            "hook": hook,
            "session_id": ctx.session_id,
            "run_id": ctx.run_id,
            "agent_type": ctx.agent_type,
            "agent_id": ctx.payload.get("agent_id") or None,
            "tool_name": ctx.payload.get("tool_name") or None,
            "reason": reason,
            "detail": detail or {},
        },
    )


def workflow_agents(setup: dict | None) -> tuple[str, ...]:
    if setup and setup.get("workflow_agents"):
        return tuple(setup["workflow_agents"])
    return WORKFLOW_AGENTS_BASE


class Deny(Exception):
    def __init__(self, hook: str, reason: str, event: str = "block", detail: dict | None = None):
        super().__init__(reason)
        self.hook = hook
        self.reason = reason
        self.event = event
        self.detail = detail or {}
