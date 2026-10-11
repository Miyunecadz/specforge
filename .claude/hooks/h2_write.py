"""H2 Write guard (BUILD_SPEC §11.3).

During an active run in this session:
- Write/Edit/MultiEdit/NotebookEdit are blocked everywhere outside the active run directory;
- script-owned and hook-owned files are blocked for everyone, including the orchestrator;
- the orchestrator (main session) may not write anywhere in the run directory;
- identified mode: a subagent may write only the agent-owned paths it owns;
- fallback mode: subagents may write agent-owned paths only.
"""

from __future__ import annotations

import os
from pathlib import Path

from _common import Deny, HookContext
from _lib import ownership

WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def target_path(ctx: HookContext) -> Path:
    ti = ctx.payload.get("tool_input") or {}
    raw = ti.get("file_path") or ti.get("notebook_path")
    if not isinstance(raw, str) or not raw:
        raise Deny("H2", "write call without a file path")
    p = Path(raw)
    if not p.is_absolute():
        p = Path(ctx.payload.get("cwd") or os.getcwd()) / p
    return Path(os.path.realpath(p))


def check(ctx: HookContext) -> None:
    target = target_path(ctx)
    runs_root = Path(os.path.realpath(ctx.runs_root))
    cls = ownership.classify(runs_root, target)
    if cls.scope != "run" or cls.run_id != ctx.run_id:
        raise Deny("H2", f"during a run nothing may be written outside the active run directory ({target})")
    if cls.kind in (ownership.SCRIPT, ownership.HOOK):
        raise Deny("H2", f"{cls.rel} is owned by {cls.owner}; it is never written with {ctx.payload.get('tool_name')}")
    if cls.kind == ownership.UNOWNED:
        raise Deny("H2", f"{cls.rel} is not in the ownership table; no one may write it")
    agent = ctx.agent_type
    if agent is None:
        raise Deny("H2", "the orchestrator writes nothing in the run directory; all its writes go through scripts")
    mode = (ctx.setup or {}).get("hook_mode", "fallback")
    if mode == "identified":
        if not ownership.agent_may_write(agent, cls.rel):
            raise Deny("H2", f"{cls.rel} is owned by {cls.owner}, not {agent}")
    # Fallback mode: agent-owned path is enough; cross-agent overwrites are caught by tamper detection.
