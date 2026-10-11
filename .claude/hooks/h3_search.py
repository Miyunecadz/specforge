"""H3 search budget and domain lists (BUILD_SPEC §11.3, §11.4). WebSearch by the researcher only (H5).

Research runs one gap at a time: run_state.py set-gap records the active gap and the limits
in budget/active_gap.json. Each allowed search is appended (hash-chained) to
budget/searches.jsonl, the hook-owned budget record; budget totals are counted from it.
Searches over the per-gap or per-run budget are blocked and logged. The config allow/deny
domain lists are applied by rewriting the call's allowed_domains/blocked_domains (Claude
Code honours updatedInput from PreToolUse hooks; probed on 2.1.296), queries that target a
denied domain are blocked, and the search mode is pinned to "standard" to bound cost.
"""

from __future__ import annotations

import json
import re

from _common import Deny, HookContext, now_iso
from _lib import hashing


def _matches(host: str, domain: str) -> bool:
    host, domain = host.lower().strip(".").removeprefix("www."), domain.lower().lstrip("*.").strip(".")
    return host == domain or host.endswith("." + domain)


def check(ctx: HookContext) -> dict:
    """Return the tool input to use (possibly rewritten). Raise Deny to block."""
    run_dir = ctx.runs_root / ctx.run_id
    ag_path = run_dir / "budget/active_gap.json"
    if not ag_path.exists():
        raise Deny("H3", "no active gap: the orchestrator must run 'run_state.py set-gap <GAP-id>' before research")
    active = json.loads(ag_path.read_text(encoding="utf-8"))
    gap, limits = active.get("gap_id"), active["limits"]
    if not gap:
        raise Deny("H3", "no gap is being researched (set-gap was cleared)")
    entries = hashing.read_jsonl(run_dir / "budget/searches.jsonl")
    per_gap = sum(1 for e in entries if e.get("gap_id") == gap)
    if per_gap >= limits["searches_per_gap"]:
        raise Deny("H3", f"search budget for {gap} is used up ({per_gap}/{limits['searches_per_gap']}); "
                         "write findings from the sources already fetched")
    if len(entries) >= limits["total_searches_per_run"]:
        raise Deny("H3", f"search budget for the run is used up ({len(entries)}/{limits['total_searches_per_run']})")
    ti = dict(ctx.payload.get("tool_input") or {})
    query = str(ti.get("query", ""))
    deny, allow = limits["deny_domains"], limits["allow_domains"]
    for d in deny:
        dom = d.lstrip("*.")
        if re.search(r"(^|[\s:/.])" + re.escape(dom.lower()) + r"($|[\s/])", query.lower()):
            raise Deny("H3", f"the query targets a denied domain ({dom})")
    allowed = [d for d in (ti.get("allowed_domains") or []) if isinstance(d, str)]
    blocked = [d for d in (ti.get("blocked_domains") or []) if isinstance(d, str)]
    if allow:
        allowed = [d for d in (allowed or [a.lstrip("*.") for a in allow]) if any(_matches(d, a) for a in allow)]
        if not allowed:
            raise Deny("H3", "the search's allowed_domains are all outside the configured allow list")
    allowed = [d for d in allowed if not any(_matches(d, x) for x in deny)]
    if not allowed:
        blocked = sorted(set(blocked) | {x.lstrip("*.") for x in deny})
    else:
        blocked = []
    new = {k: v for k, v in ti.items() if k not in ("allowed_domains", "blocked_domains", "mode")}
    if allowed:
        new["allowed_domains"] = allowed
    if blocked:
        new["blocked_domains"] = blocked
    new["mode"] = "standard"
    hashing.append_chained(run_dir / "budget/searches.jsonl", {
        "schema_version": 1, "kind": "search", "ts": now_iso(), "run_id": ctx.run_id, "gap_id": gap, "query": query,
        "allowed_domains": allowed, "blocked_domains": blocked, "agent_id": ctx.payload.get("agent_id")})
    return new
