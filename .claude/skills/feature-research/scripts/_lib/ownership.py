"""The single-writer ownership table (BUILD_SPEC §5, File ownership). Stdlib only.

This module is the one machine-readable copy of the table. Hook H2, run_state.py tamper
reports, and the tests all read it. Lock files (`X.lock`) and temporary files
(`.X.<random>.tmp`) belong to the owner of `X`.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SCRIPT = "script"
HOOK = "hook"
AGENT = "agent"
UNOWNED = "unowned"

# Files directly under <runs-root>.
ROOT_RULES: list[tuple[str, str, str]] = [
    (".active_run", "run_state.py", SCRIPT),
    (".heartbeat", "hooks", HOOK),
    (".hook_events.jsonl", "hooks", HOOK),
]

# Files under <runs-root>/<run-id>/. First match wins.
RUN_RULES: list[tuple[str, str, str]] = [
    ("run_manifest.json", "run_state.py", SCRIPT),
    ("log.jsonl", "run_state.py", SCRIPT),
    ("input/**", "run_state.py", SCRIPT),
    ("warnings.json", "run_state.py", SCRIPT),
    ("run_summary.json", "run_state.py", SCRIPT),
    ("budget/active_gap.json", "run_state.py", SCRIPT),
    ("integrity/run_state.json", "run_state.py", SCRIPT),
    ("history/**", "run_state.py", SCRIPT),
    ("capture/**", "capture_mockup.py", SCRIPT),
    ("checkpoints/**", "status_rules.py", SCRIPT),
    ("decisions.json", "status_rules.py", SCRIPT),
    ("status_registry.json", "status_rules.py", SCRIPT),
    ("status_history.jsonl", "status_rules.py", SCRIPT),
    ("status_labels.json", "status_rules.py", SCRIPT),
    ("integrity/status_rules.json", "status_rules.py", SCRIPT),
    ("sources/**", "fetch_source.py", SCRIPT),
    ("fetch_log.jsonl", "fetch_source.py", SCRIPT),
    ("budget/fetches-*.json", "fetch_source.py", SCRIPT),
    ("integrity/fetch_source.json", "fetch_source.py", SCRIPT),
    ("budget/searches.jsonl", "hooks", HOOK),
    ("citation_check.json", "verify_citations.py", SCRIPT),
    ("validation.json", "check_spec.py", SCRIPT),
    ("inventory.json", "mockup-extractor", AGENT),
    ("requirements.json", "requirements-parser", AGENT),
    ("gaps.json", "gap-analyst", AGENT),
    ("findings/*.json", "web-researcher", AGENT),
    ("fetch_requests/*.json", "web-researcher-fallback", AGENT),
    ("verified_findings.json", "source-verifier", AGENT),
    ("feasibility.json", "feasibility-analyst", AGENT),
    ("questions.json", "question-generator", AGENT),
    ("spec.md", "doc-writer", AGENT),
    ("review.json", "doc-reviewer", AGENT),
    ("warnings/*.json", "<agent>", AGENT),
]

# findings/** is written by whichever researcher variant is installed (§5).
RESEARCHER_VARIANTS = ("web-researcher", "web-researcher-fallback")

_TMP_RE = re.compile(r"^\.(?P<name>.+)\.[^.]+\.tmp$")


@dataclass(frozen=True)
class Classification:
    scope: str  # "root" (directly under runs-root), "run" (inside a run dir), "outside"
    run_id: str | None
    rel: str | None  # path relative to the run dir (or runs-root for scope "root")
    owner: str | None
    kind: str  # SCRIPT, HOOK, AGENT, UNOWNED


def _base_name(rel: PurePosixPath) -> PurePosixPath:
    """Map lock and temp files onto the file they protect."""
    name = rel.name
    if name.endswith(".lock"):
        name = name[: -len(".lock")]
    else:
        m = _TMP_RE.match(name)
        if m:
            name = m.group("name")
    return rel.with_name(name)


def _match(rel: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return rel == prefix or rel.startswith(prefix + "/")
    # fnmatch's * crosses "/"; require the same depth so findings/*.json is one level.
    if rel.count("/") != pattern.count("/"):
        return False
    return fnmatch.fnmatchcase(rel, pattern)


def owner_of_run_path(rel: str) -> tuple[str | None, str]:
    base = str(_base_name(PurePosixPath(rel)))
    for pattern, owner, kind in RUN_RULES:
        if _match(base, pattern):
            if owner == "<agent>":
                owner = PurePosixPath(base).stem
            return owner, kind
    return None, UNOWNED


def classify(runs_root: Path, path: Path) -> Classification:
    """Classify an absolute, already-resolved path against a runs root."""
    try:
        rel = PurePosixPath(path.relative_to(runs_root).as_posix())
    except ValueError:
        return Classification("outside", None, None, None, UNOWNED)
    parts = rel.parts
    if len(parts) == 0:
        return Classification("root", None, "", None, UNOWNED)
    if len(parts) == 1:
        base = str(_base_name(rel))
        for name, owner, kind in ROOT_RULES:
            if base == name:
                return Classification("root", None, str(rel), owner, kind)
        # A bare run directory name or any other file directly under runs-root.
        return Classification("root", None, str(rel), None, UNOWNED)
    run_id = parts[0]
    inner = str(PurePosixPath(*parts[1:]))
    owner, kind = owner_of_run_path(inner)
    return Classification("run", run_id, inner, owner, kind)


def agent_may_write(agent_type: str, rel: str) -> bool:
    """True if the subagent `agent_type` owns run-relative path `rel`."""
    owner, kind = owner_of_run_path(rel)
    if kind != AGENT or owner is None:
        return False
    if owner == "web-researcher" and str(_base_name(PurePosixPath(rel))).startswith("findings/"):
        return agent_type in RESEARCHER_VARIANTS
    return owner == agent_type
