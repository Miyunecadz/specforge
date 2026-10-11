"""Stage table (BUILD_SPEC §7): who performs each stage, its outputs and their schemas.

Output patterns are run-relative. A trailing "?" marks an optional output. "dir/**" means
every file under dir. Stages whose implementation belongs to a later phase are listed
with available=False, and run_state.py refuses to start them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Stage:
    key: str
    name: str
    kind: str  # "script", "agent", "checkpoint", "mixed"
    outputs: tuple[str, ...]
    schemas: dict = field(default_factory=dict)
    agent: str | None = None
    available: bool = False


STAGES: dict[str, Stage] = {
    "1": Stage("1", "Intake", "script", ("input/**",), {"input/request.json": "request"}, available=True),
    "2": Stage(
        "2", "Capture mockup", "script", ("capture/**",),
        {"capture/manifest.json": "capture_manifest"}, available=True,
    ),
    "3": Stage(
        "3", "Extract inventory", "agent", ("inventory.json", "warnings/mockup-extractor.json?"),
        {"inventory.json": "inventory", "warnings/mockup-extractor.json": "warnings"},
        agent="mockup-extractor", available=True,
    ),
    "4": Stage("4", "Parse requirements", "agent", ("requirements.json",), agent="requirements-parser"),
    "5": Stage("5", "Checkpoint 1: confirm requirements", "checkpoint", ()),
    "6": Stage("6", "Analyse gaps", "agent", ("gaps.json",), agent="gap-analyst"),
    "7": Stage("7", "Checkpoint 2: approve gaps and routing", "checkpoint", ()),
    "8": Stage("8", "Research", "agent", ("findings/**",), agent="web-researcher"),
    "9": Stage("9", "Mechanical citation check", "script", ("citation_check.json",)),
    "10": Stage("10", "Semantic verification", "agent", ("verified_findings.json",), agent="source-verifier"),
    "11": Stage("11", "Feasibility and cross-cutting analysis", "agent", ("feasibility.json",), agent="feasibility-analyst"),
    "12": Stage("12", "Generate customer questions", "agent", ("questions.json",), agent="question-generator"),
    "13": Stage("13", "Checkpoint 3: product decisions", "checkpoint", ()),
    "13R": Stage("13R", "Re-confirmation checkpoint", "checkpoint", ()),
    "14": Stage("14", "Write specification", "agent", ("spec.md",), agent="doc-writer"),
    "15": Stage("15", "Review and validate", "mixed", ("validation.json", "review.json"), agent="doc-reviewer"),
    "16": Stage("16", "Report", "script", ("run_summary.json",)),
}

ORDER = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "13R", "14", "15", "16"]
OPTIONAL_STAGES = {"13R"}


def expand_outputs(run_dir: Path, stage: Stage) -> tuple[dict[str, Path], list[str]]:
    """Return (existing outputs rel->path, missing required patterns)."""
    found: dict[str, Path] = {}
    missing: list[str] = []
    for pattern in stage.outputs:
        optional = pattern.endswith("?")
        pat = pattern.rstrip("?")
        if pat.endswith("/**"):
            base = run_dir / pat[:-3]
            files = [p for p in sorted(base.rglob("*")) if p.is_file() and not _transient(p)] if base.is_dir() else []
            if not files and not optional:
                missing.append(pat)
            for p in files:
                found[p.relative_to(run_dir).as_posix()] = p
        else:
            p = run_dir / pat
            if p.is_file():
                found[pat] = p
            elif not optional:
                missing.append(pat)
    return found, missing


def _transient(p: Path) -> bool:
    return p.name.endswith(".lock") or (p.name.startswith(".") and p.name.endswith(".tmp"))


def semantic_checks(run_dir: Path, stage: Stage, manifest: dict) -> list[str]:
    """Mechanical checks beyond schema validation."""
    problems: list[str] = []
    if stage.key == "3":
        inv = json.loads((run_dir / "inventory.json").read_text(encoding="utf-8"))
        cap = json.loads((run_dir / "capture/manifest.json").read_text(encoding="utf-8"))
        if inv.get("run_id") != manifest["run_id"]:
            problems.append("inventory.json run_id does not match the run")
        if inv.get("capture_status") != cap.get("status"):
            problems.append(
                f"inventory.json capture_status {inv.get('capture_status')!r} does not match "
                f"capture/manifest.json status {cap.get('status')!r}"
            )
        ids: list[str] = []
        for section in ("screens", "components", "flows", "data_entities"):
            ids += [item["id"] for item in inv.get(section, [])]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            problems.append(f"duplicate SCR ids: {', '.join(dupes)}")
        known = set(ids)
        for amb in inv.get("ambiguous_behaviours", []):
            if amb["element_ref"] not in known:
                problems.append(f"ambiguous_behaviours element_ref {amb['element_ref']} is not an inventory id")
        for ref in _evidence_refs(inv):
            target = (run_dir / ref["artifact"]).resolve()
            if run_dir.resolve() not in target.parents or not target.is_file():
                problems.append(f"evidence artifact does not exist in the run: {ref['artifact']}")
    return problems


def _evidence_refs(obj: object):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("evidence_refs", "source_refs") and isinstance(v, list):
                for ref in v:
                    if isinstance(ref, dict) and "artifact" in ref:
                        yield ref
            else:
                yield from _evidence_refs(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _evidence_refs(v)
