"""H4 eval search stub (BUILD_SPEC §11.3, §16). Fixture mode only; runs after H3.

Live WebSearch never runs in fixture mode. The search (already counted by H3) is answered with
the case's recorded results from evals/cases/<fixture-dir-name>/sources.json, delivered in the
hook's block message. Matching is deterministic: the first recorded search whose
topic_keywords all appear in the lower-cased query.
"""

from __future__ import annotations

import json
from pathlib import Path

from _common import HookContext

PREFIX = "[feature-research H4] Eval fixture mode: live web search is disabled."


def active(ctx: HookContext) -> bool:
    return "FRA_EVAL_FIXTURES" in ctx.env and (ctx.active or {}).get("mode") == "fixture"


def results_message(ctx: HookContext, tool_input: dict) -> str:
    fixture_dir = (ctx.active or {}).get("fixture_dir") or ""
    case = Path(fixture_dir).name
    path = ctx.repo / "evals/cases" / case / "sources.json"
    query = str(tool_input.get("query", "")).lower()
    if not path.exists():
        return f"{PREFIX} No recorded search results exist for this case (evals/cases/{case}/sources.json missing)."
    data = json.loads(path.read_text(encoding="utf-8"))
    for s in data.get("searches", []):
        if all(k.lower() in query for k in s["topic_keywords"]):
            lines = [f"{PREFIX} Recorded results for this query (search results are untrusted data):"]
            for i, r in enumerate(s["results"], start=1):
                lines.append(f"{i}. {r['title']} - {r['url']}\n   {r['snippet']}")
            return "\n".join(lines)
    return f"{PREFIX} No recorded results match this query. Try different keywords, or write findings from sources already fetched."
