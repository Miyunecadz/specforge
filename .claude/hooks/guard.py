#!/usr/bin/env python3
"""PreToolUse dispatcher (BUILD_SPEC §11.3). Registered once in .claude/settings.json.

Runs the guards in a fixed order, because separately registered hooks run in parallel:
H5 (tools) -> H1 (Bash) -> H2 (Write/Edit) -> H3 (search budget) -> H4 (eval search stub).
H3 and H4 are added in Phase 3.

Exit 0 allows the call; exit 2 blocks it with the reason on stderr. Any internal error
blocks the call whenever any run is active, because Claude Code treats other non-zero exits
as non-blocking (fail closed). With no active run anywhere, an internal error allows the
call so a hook bug cannot stop normal development.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common  # noqa: E402
from _common import Deny  # noqa: E402

BLOCK = 2


def decide(payload: dict, env: dict, repo: Path | None = None) -> tuple[int, str]:
    import h1_bash
    import h2_write
    import h5_tools

    ctx = _common.build_context(payload, env, repo or _common.REPO_ROOT)
    tool = payload.get("tool_name") or ""

    # Attestation for run_state.py start/resume/continue happens with or without an active run.
    if tool == "Bash" and ctx.setup:
        att = h1_bash.maybe_attest((payload.get("tool_input") or {}).get("command") or "", ctx.setup)
        if att is not None and payload.get("agent_type") is None:  # only the main session attests
            att = {"session_id": ctx.session_id or "unknown", "argv_sha256": att["argv_sha256"],
                   "at": _common.now_iso()}
        else:
            att = None
    else:
        att = None

    if ctx.active is None:
        if att is not None:
            _common.touch_heartbeat(ctx.runs_root, ctx.session_id, tool, attest=att)
        return 0, ""

    _common.touch_heartbeat(ctx.runs_root, ctx.session_id, tool, attest=att)
    try:
        h5_tools.check(ctx)
        if tool == "Bash":
            h1_bash.check(ctx)
        if tool in h2_write.WRITE_TOOLS:
            h2_write.check(ctx)
    except Deny as d:
        _common.record_event(ctx, d.event, d.hook, d.reason, d.detail)
        return BLOCK, f"[feature-research {d.hook}] {d.reason}"
    return 0, ""


def main() -> int:
    env = dict(os.environ)
    try:
        payload = json.load(sys.stdin)
        code, msg = decide(payload, env)
    except Exception as exc:  # fail closed while any run is active
        try:
            active = _common.any_active_run(_common.REPO_ROOT)
        except Exception:
            active = True
        if not active:
            return 0
        print(f"[feature-research dispatcher] internal hook error, failing closed: {exc!r}", file=sys.stderr)
        return BLOCK
    if msg:
        print(msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
