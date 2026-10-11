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
    "4": Stage("4", "Parse requirements", "agent", ("requirements.json", "warnings/requirements-parser.json?"),
               {"requirements.json": "requirements", "warnings/requirements-parser.json": "warnings"},
               agent="requirements-parser", available=True),
    "5": Stage("5", "Checkpoint 1: confirm requirements", "checkpoint", ("checkpoints/checkpoint-1-answers.json",),
               {"checkpoints/checkpoint-1-answers.json": "checkpoint_file"}, available=True),
    "6": Stage("6", "Analyse gaps", "agent", ("gaps.json", "warnings/gap-analyst.json?"),
               {"gaps.json": "gaps", "warnings/gap-analyst.json": "warnings"}, agent="gap-analyst", available=True),
    "7": Stage("7", "Checkpoint 2: approve gaps and routing", "checkpoint", ("checkpoints/checkpoint-2-answers.json",),
               {"checkpoints/checkpoint-2-answers.json": "checkpoint_file"}, available=True),
    "8": Stage("8", "Research", "agent", ("findings/**?", "sources/**?", "fetch_requests/**?", "warnings/web-researcher.json?",
                                          "warnings/web-researcher-fallback.json?"),
               {"warnings/web-researcher.json": "warnings", "warnings/web-researcher-fallback.json": "warnings"},
               agent="web-researcher", available=True),
    "9": Stage("9", "Mechanical citation check", "script", ("citation_check.json",),
               {"citation_check.json": "citation_check"}, available=True),
    "10": Stage("10", "Semantic verification", "agent", ("verified_findings.json", "warnings/source-verifier.json?"),
                {"verified_findings.json": "verified_findings", "warnings/source-verifier.json": "warnings"},
                agent="source-verifier", available=True),
    "11": Stage("11", "Feasibility and cross-cutting analysis", "agent", ("feasibility.json", "warnings/feasibility-analyst.json?"),
                {"feasibility.json": "feasibility", "warnings/feasibility-analyst.json": "warnings"},
                agent="feasibility-analyst", available=True),
    "12": Stage("12", "Generate customer questions", "agent", ("questions.json", "warnings/question-generator.json?"),
                {"questions.json": "questions", "warnings/question-generator.json": "warnings"},
                agent="question-generator", available=True),
    "13": Stage("13", "Checkpoint 3: product decisions", "checkpoint", ("checkpoints/checkpoint-3-answers.json",),
                {"checkpoints/checkpoint-3-answers.json": "checkpoint_file"}, available=True),
    "13R": Stage("13R", "Re-confirmation checkpoint", "checkpoint", ("checkpoints/checkpoint-13R-answers.json",),
                 {"checkpoints/checkpoint-13R-answers.json": "checkpoint_file"}, available=True),
    "14": Stage("14", "Write specification", "agent", ("spec.md",), agent="doc-writer"),
    "15": Stage("15", "Review and validate", "mixed", ("validation.json", "review.json"), agent="doc-reviewer"),
    "16": Stage("16", "Report", "script", ("run_summary.json",)),
}

CHECKPOINT_OF_STAGE = {"5": "1", "7": "2", "13": "3", "13R": "13R"}
STAGE_OF_CHECKPOINT = {v: k for k, v in CHECKPOINT_OF_STAGE.items()}

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


def _registry(run_dir: Path) -> dict:
    p = run_dir / "status_registry.json"
    return json.loads(p.read_text(encoding="utf-8"))["items"] if p.exists() else {}


def _schema_errors(name: str, path: Path) -> list[str]:
    from . import schema
    return schema.errors(name, json.loads(path.read_text(encoding="utf-8")))


def research_gaps(run_dir: Path) -> set:
    p = run_dir / "status_labels.json"
    if not p.exists():
        return set()
    return {g for g, r in json.loads(p.read_text(encoding="utf-8"))["gap_routing"].items() if r["research_allowed"]}


def stale_approved(run_dir: Path) -> list:
    return sorted(i for i, it in _registry(run_dir).items() if it.get("stale") and it.get("approval") == "approved")


def skip_allowed(run_dir: Path, key: str) -> str | None:
    """Return None if the stage may be skipped, otherwise the reason it may not."""
    if key == "13R":
        return None if not stale_approved(run_dir) else "approved items are stale and must be presented for re-confirmation"
    if key == "8":
        return None if not research_gaps(run_dir) else "gaps are approved for research"
    if key == "10":
        pending = [i for i, it in _registry(run_dir).items() if it.get("verification") == "pending"]
        return None if not pending else "findings are pending semantic verification"
    if key == "9":
        return None if not research_gaps(run_dir) and not (run_dir / "findings").exists() else "there are findings to check"
    return "this stage cannot be skipped"


def _registered(run_dir: Path, rel: str) -> bool:
    from . import hashing
    reg = run_dir / "status_registry.json"
    if not reg.exists():
        return False
    return json.loads(reg.read_text(encoding="utf-8"))["registered_artifacts"].get(rel) == hashing.sha256_file(run_dir / rel)


def semantic_checks(run_dir: Path, stage: Stage, manifest: dict) -> list[str]:
    """Mechanical checks beyond schema validation."""
    problems: list[str] = []
    if stage.key == "1":
        req = json.loads((run_dir / "input/request.json").read_text(encoding="utf-8"))
        if req.get("prior_decisions"):
            dec = run_dir / "decisions.json"
            ok = dec.exists() and any(d["source"] == "prior_decisions_file"
                                      for d in json.loads(dec.read_text(encoding="utf-8"))["decisions"])
            if not ok:
                problems.append("prior decisions were supplied but not recorded: run 'status_rules.py decide --prior'")
    if stage.key in ("4", "6"):
        rel = "requirements.json" if stage.key == "4" else "gaps.json"
        doc = json.loads((run_dir / rel).read_text(encoding="utf-8"))
        if doc.get("run_id") != manifest["run_id"]:
            problems.append(f"{rel} run_id does not match the run")
        if not _registered(run_dir, rel):
            problems.append(f"{rel} (this version) is not registered: run 'status_rules.py register {rel}'")
        if stage.key == "4":
            src = (run_dir / "input/requirements.md").read_text(encoding="utf-8")
            norm = " ".join(src.split())
            for r in doc["requirements"]:
                if " ".join(r["source_quote"].split()) not in norm:
                    problems.append(f"{r['id']} source_quote is not an exact quote from input/requirements.md")
    if stage.key == "8":
        allowed = research_gaps(run_dir)
        files = {p.stem for p in (run_dir / "findings").glob("*.json")} if (run_dir / "findings").is_dir() else set()
        for g in sorted(files - allowed):
            problems.append(f"findings/{g}.json exists but {g} is not approved for research")
        for g in sorted(allowed - files):
            problems.append(f"{g} is approved for research but has no findings/{g}.json (write one, even with no findings)")
        for g in sorted(files & allowed):
            schema_errs = _schema_errors("findings", run_dir / f"findings/{g}.json")
            if schema_errs:
                problems.append(f"findings/{g}.json: {schema_errs[0]}")
            elif not _registered(run_dir, f"findings/{g}.json"):
                problems.append(f"findings/{g}.json (this version) is not registered: run 'status_rules.py register findings/{g}.json'")
    if stage.key == "9":
        cc = json.loads((run_dir / "citation_check.json").read_text(encoding="utf-8"))
        reg = _registry(run_dir)
        for r in cc["results"]:
            want = "citation_failed" if not r["passed"] else "pending"
            got = reg.get(r["finding_id"], {}).get("verification")
            if not r["passed"] and got != "citation_failed":
                problems.append(f"{r['finding_id']} failed the citation check but is {got}: run 'status_rules.py verification --from citations'")
    if stage.key == "10":
        pending = sorted(i for i, it in _registry(run_dir).items() if it.get("verification") == "pending")
        if pending:
            problems.append(f"findings still pending verification: {', '.join(pending)}; run 'status_rules.py verification --from semantic'")
    if stage.key == "11":
        if not _registered(run_dir, "feasibility.json"):
            problems.append("feasibility.json (this version) is not registered: run 'status_rules.py register feasibility.json'")
    if stage.key == "12":
        import yaml
        cfg_p = run_dir / "input/config.yaml"
        limit = yaml.safe_load(cfg_p.read_text(encoding="utf-8"))["review"]["max_customer_questions"] if cfg_p.exists() else 10
        qs = json.loads((run_dir / "questions.json").read_text(encoding="utf-8"))
        if qs["run_id"] != manifest["run_id"]:
            problems.append("questions.json run_id does not match the run")
        if len(qs["questions"]) > limit:
            problems.append(f"{len(qs['questions'])} questions exceed max_customer_questions={limit}; fold minor ones into implementation_details")
        reg = _registry(run_dir)
        ids = [q["id"] for q in qs["questions"]]
        if ids != [f"Q-{n:03d}" for n in range(1, len(ids) + 1)]:
            problems.append("question ids must be Q-001, Q-002, ... in order")
        order = {"critical": 0, "important": 1, "optional": 2}
        if [order[q["priority"]] for q in qs["questions"]] != sorted(order[q["priority"]] for q in qs["questions"]):
            problems.append("questions must be ordered by priority (critical, important, optional)")
        for q in qs["questions"]:
            for a in q["affected_ids"]:
                if a.startswith(("REQ-", "GAP-", "F-", "FEA-", "ASM-")) and a not in reg:
                    problems.append(f"{q['id']} affects unknown item {a}")
            if q["recommendation"]:
                bad = [f for f in q["recommendation"]["finding_ids"] if reg.get(f, {}).get("verification") != "kept"]
                if bad:
                    problems.append(f"{q['id']} recommendation cites findings that are not kept: {', '.join(bad)}")
                if q["recommendation"]["option"] not in [o["option"] for o in q["options"]]:
                    problems.append(f"{q['id']} recommends an option that is not listed")
    if stage.key in ("5", "7", "13", "13R"):
        if manifest.get("open_checkpoint") != CHECKPOINT_OF_STAGE[stage.key]:
            problems.append("the checkpoint was never opened with run_state.py await-user")
        if stage.key == "5":
            reqs = json.loads((run_dir / "requirements.json").read_text(encoding="utf-8"))
            cp = json.loads((run_dir / "checkpoints/checkpoint-1-answers.json").read_text(encoding="utf-8"))
            answered = set()
            for rnd in cp["rounds"]:
                for a in rnd["answers"]:
                    if any(x["type"] != "leave_open" for x in a["actions"]) or not a["actions"]:
                        answered.update(a.get("question_ids", []))
            for q in reqs["clarifying_questions"]:
                if q["blocking"] and q["id"] not in answered:
                    problems.append(f"blocking question {q['id']} has no recorded answer; it cannot be bypassed")
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
