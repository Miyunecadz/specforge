#!/usr/bin/env python3
"""SubagentStart recorder (BUILD_SPEC §5, §11.3).

Records every subagent invocation (agent type, agent id, current stage) in
.hook_events.jsonl while a run is active in this session. run_state.py stage --complete
refuses to complete an agent stage without a matching record.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common  # noqa: E402


def record(payload: dict, env: dict, repo: Path | None = None) -> bool:
    ctx = _common.build_context(payload, env, repo or _common.REPO_ROOT)
    if ctx.active is None:
        return False
    stage = None
    manifest = ctx.runs_root / ctx.run_id / "run_manifest.json"
    if manifest.exists():
        stage = json.loads(manifest.read_text(encoding="utf-8")).get("current_stage")
    _common.touch_heartbeat(ctx.runs_root, ctx.session_id, "SubagentStart")
    _common.record_event(ctx, "subagent_start", "recorder", None, {"stage": stage})
    return True


def main() -> int:
    try:
        record(json.load(sys.stdin), dict(os.environ))
    except Exception as exc:
        print(f"[feature-research recorder] could not record subagent start: {exc!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
