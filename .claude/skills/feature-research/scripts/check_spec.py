#!/usr/bin/env python3
"""check_spec.py --run <run-id> --round <n> [--final]: mechanical spec checks (BUILD_SPEC §9.12, §9.13 [code]).

Parses spec.md with the §9.12 line format and checks, against status_labels.json, the
registry, decisions.json and inventory.json:
  1  every REQ appears in Requirements Traceability with a treatment
  2  every approved gap appears in Gaps Identified as addressed or open
  4  every Research tag in the main body references a finding with verification kept;
     dropped / citation-failed findings appear only under Sources > Limitations
  6  every FR/NFR/BR/AC bullet follows the line format, first tag labelled, (draft) correct
  7  every tag references an existing id; line ids unique
  8  labels equal the derived labels (most recent DEC); placement matches the derived placement
  9  every ASM id and every stale item appears in Open Questions & Assumptions
  15 all template sections present
--final checks only the last pass: section 1 shows the publication status computed by
run_state.py report, and nothing outside section 1 changed since the last recorded revision.
Writes validation.json. Exit 0 when every blocking check passes, 1 otherwise, 3 refused.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import fsutil, paths, runctx, schema  # noqa: E402
from _lib.runctx import RunError, now_iso  # noqa: E402

SECTIONS = ["Document Status", "Executive Summary", "Goals and Scope", "Users and Roles", "Existing Mockup Coverage",
            "Requirements Traceability", "Gaps Identified", "Functional Requirements", "State Transitions and Edge Cases",
            "Non-Functional Requirements", "Data Model and Business Rules", "Screens and User Flows",
            "Integrations and Dependencies", "Security, Privacy, and Error Handling", "Decisions Log",
            "Open Questions and Assumptions", "Research Findings and Recommendations", "Sources"]
ID = r"(?:REQ-\d{3,}|SCR-\d{3,}|F-GAP-\d{3,}-\d{2,}|FEA-\d{3,}|ASM-[PGFW]-\d{3,}|DEC-\d{3,}|GAP-\d{3,})"
TAG_RE = re.compile(r"\[(Customer|Mockup|Research|Decision|Inferred|Assumption): (" + ID + r")(?: · ([^\]]+))?\]")
ANY_TAGLIKE = re.compile(r"\[(?:Customer|Mockup|Research|Decision|Inferred|Assumption):[^\]]*\]")
LINE_RE = re.compile(r"^- \*\*((?:FR|NFR|BR|AC)-\d{3,})\*\* (\(draft\) )?(.+?) ((?:\[[^\]]+\] ?)+)$")
LINE_START = re.compile(r"^\s*- \*\*(?:FR|NFR|BR|AC)-")
TREATMENTS = ("partially addressed", "addressed", "unresolved", "out of scope")
MAIN_BODY = {8, 9, 10, 11, 12, 13, 14, 17}
FIRM = ("Approved", "Decided", "Explicit")


class Doc:
    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.section_of: list[tuple[int | None, str | None]] = []
        self.headings: dict[int, str] = {}
        sec, sub = None, None
        in_block = False
        for line in self.lines:
            if line.startswith("```"):
                in_block = not in_block
            m = re.match(r"^## (\d+)\. (.+?)\s*$", line) if not in_block else None
            if m:
                sec, sub = int(m.group(1)), None
                self.headings[sec] = m.group(2)
            elif not in_block and line.startswith("### "):
                sub = line[4:].strip()
            self.section_of.append((sec, sub))

    def zone(self, i: int) -> str:
        sec, sub = self.section_of[i]
        if sec == 3 and sub and sub.lower().startswith("out of scope"):
            return "out_of_scope_rejected"
        if sec == 3 and sub and sub.lower().startswith("deferred"):
            return "deferred"
        if sec == 3 and sub and sub.lower() in ("goals", "in scope"):
            return "main_body"
        if sec == 15:
            return "decisions_log"
        if sec == 18 and sub and sub.lower().startswith("limitations"):
            return "sources_limitations"
        if sec in MAIN_BODY:
            return "main_body"
        return "neutral"

    def section_text(self, n: int) -> str:
        return "\n".join(l for l, (s, _) in zip(self.lines, self.section_of) if s == n)


def asm_w_block(text: str) -> list | None:
    m = re.search(r"```json asm-w\n(.*?)\n```", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    return data if isinstance(data, list) else None


def check(run_dir: Path, text: str) -> list[dict]:
    doc = Doc(text)
    labels = json.loads((run_dir / "status_labels.json").read_text(encoding="utf-8"))
    derived = labels["items"]
    reg = json.loads((run_dir / "status_registry.json").read_text(encoding="utf-8"))["items"]
    decs = {d["id"] for d in json.loads((run_dir / "decisions.json").read_text(encoding="utf-8"))["decisions"]} \
        if (run_dir / "decisions.json").exists() else set()
    inv = json.loads((run_dir / "inventory.json").read_text(encoding="utf-8")) if (run_dir / "inventory.json").exists() else {}
    scr = {o["id"] for k in ("screens", "components", "flows", "data_entities") for o in inv.get(k, [])}
    ev = {n: [] for n in (1, 2, 4, 6, 7, 8, 9, 15)}

    def exists(i):
        return i in reg or i in scr or i in decs

    def derived_label(i):
        if i.startswith("SCR-"):
            return "Observed", "main_body"
        d = derived.get(i)
        return (d["label"], d["placement"]) if d else (None, None)

    # 15: sections
    for n, title in enumerate(SECTIONS, start=1):
        if doc.headings.get(n, "").strip().lower() != title.lower():
            ev[15].append(f"missing or misnamed section '## {n}. {title}'")
    for sub in ("Out of Scope / Rejected", "Deferred"):
        if not any(s == 3 and (b or "").lower() == sub.lower() for s, b in doc.section_of):
            ev[15].append(f"missing '### {sub}' under Goals and Scope")
    if not any(s == 18 and (b or "").lower() == "limitations" for s, b in doc.section_of):
        ev[15].append("missing '### Limitations' under Sources")

    # 6, 7, 8, 4: line format, ids, labels, placement
    line_ids: list[str] = []
    for i, line in enumerate(doc.lines):
        zone = doc.zone(i)
        sec = doc.section_of[i][0]
        if LINE_START.match(line):
            m = LINE_RE.match(line.strip())
            if not m:
                ev[6].append(f"line {i + 1}: does not follow '- **ID** [(draft) ]statement [tag]...': {line.strip()[:90]}")
                continue
            lid, draft, _stmt, tagstr = m.groups()
            line_ids.append(lid)
            tags = TAG_RE.findall(tagstr)
            if len(tags) != len(ANY_TAGLIKE.findall(tagstr)) or not tags:
                ev[6].append(f"line {i + 1} {lid}: malformed tag")
                continue
            src, item, label = tags[0]
            if not label:
                ev[6].append(f"line {i + 1} {lid}: first tag has no label")
            elif item.startswith("DEC-"):
                ev[6].append(f"line {i + 1} {lid}: the first tag must name the line's primary item, not a decision")
            else:
                want, _ = derived_label(item)
                if want and label.strip() != want:
                    ev[8].append(f"line {i + 1} {lid}: label '{label.strip()}' for {item}, derived '{want}'")
                if lid.startswith("AC-"):
                    firm = any(label.strip().startswith(f) for f in FIRM)
                    if firm and draft:
                        ev[6].append(f"line {i + 1} {lid}: '(draft)' on an AC whose primary item is {label.strip()}")
                    if not firm and not draft:
                        ev[6].append(f"line {i + 1} {lid}: AC whose primary item is '{label.strip()}' must be marked (draft)")
                elif draft:
                    ev[6].append(f"line {i + 1} {lid}: '(draft)' is only for AC lines")
        # all tags anywhere
        for src, item, label in TAG_RE.findall(line):
            if not exists(item):
                ev[7].append(f"line {i + 1}: {item} does not exist in the run artifacts")
                continue
            if item.startswith("DEC-"):
                continue
            want, place = derived_label(item)
            if label and want and label.strip() != want:
                ev[8].append(f"line {i + 1}: label '{label.strip()}' for {item}, derived '{want}'")
            if place == "nowhere":
                ev[8].append(f"line {i + 1}: {item} is pending verification and may not appear in the spec")
            if zone == "main_body" and place and place != "main_body":
                n = 4 if item.startswith("F-") and place == "sources_limitations" else 8
                ev[n].append(f"line {i + 1}: {item} ({want}) belongs in {place}, not the main body")
            if zone in ("out_of_scope_rejected", "deferred", "sources_limitations") and place and place != zone \
                    and not (zone == "out_of_scope_rejected" and item.startswith("REQ-")):
                ev[8].append(f"line {i + 1}: {item} ({want}) is under {zone} but its placement is {place}")
            if zone == "main_body" and src == "Research" and item.startswith("F-"):
                if reg.get(item, {}).get("verification") != "kept":
                    ev[4].append(f"line {i + 1}: Research tag {item} in the main body is not a kept finding")
            research_item = item.startswith("F-") or reg.get(item, {}).get("provenance") == "research_evidence"
            if (src == "Research") != research_item and not (src == "Decision" and research_item) \
                    or (src == "Mockup") != item.startswith("SCR-") or (src == "Assumption") != item.startswith("ASM-"):
                ev[6].append(f"line {i + 1}: source '{src}' does not match {item}")
        for m in re.finditer(r"\b(F-GAP-\d{3,}-\d{2,})\b", line):
            f = m.group(1)
            v = reg.get(f, {}).get("verification")
            if v in ("dropped", "citation_failed") and zone not in ("sources_limitations", "neutral", "decisions_log"):
                ev[4].append(f"line {i + 1}: {f} is {v}; it may appear only under Sources > Limitations")
    dupes = sorted({x for x in line_ids if line_ids.count(x) > 1})
    if dupes:
        ev[7].append(f"duplicate line ids: {', '.join(dupes)}")
    # state-transition tables: provenance column must hold a valid tag
    for i, line in enumerate(doc.lines):
        if doc.section_of[i][0] == 9 and line.startswith("|") and not re.match(r"^\|\s*(State|---)", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 5 and not TAG_RE.search(cells[-1]):
                ev[6].append(f"line {i + 1}: state-transition row has no valid provenance tag")

    # 1: requirements traceability
    trace = [l.lower() for l in doc.section_text(6).splitlines()]
    for rid in sorted(i for i in reg if i.startswith("REQ-")):
        rows = [l for l in trace if re.search(rf"\b{rid.lower()}\b", l)]
        if not rows:
            ev[1].append(f"{rid} is missing from Requirements Traceability")
        elif not any(t in r for r in rows for t in TREATMENTS):
            ev[1].append(f"{rid} has no treatment (addressed / partially addressed / unresolved / out of scope)")
    # 2: approved gaps
    gaps_text = [l.lower() for l in doc.section_text(7).splitlines()]
    for gid in sorted(i for i, it in reg.items() if i.startswith("GAP-") and it["approval"] == "approved"):
        rows = [l for l in gaps_text if re.search(rf"\b{gid.lower()}\b", l)]
        if not rows or not any(("addressed" in r or "open" in r) for r in rows):
            ev[2].append(f"approved {gid} is not shown as addressed or open in Gaps Identified")
    # 9: ASM ids and stale items in Open Questions
    open_q = doc.section_text(16)
    used_asm = set(re.findall(r"\bASM-[PGFW]-\d{3,}\b", text))
    for a in sorted(used_asm):
        if a not in open_q:
            ev[9].append(f"{a} is used but not listed in Open Questions and Assumptions")
    for s in sorted(i for i, it in reg.items() if it["stale"] and it["approval"] == "approved"):
        if s not in open_q:
            ev[9].append(f"stale item {s} is not listed in Open Questions and Assumptions")
    block = asm_w_block(text)
    used_w = {a for a in used_asm if a.startswith("ASM-W-")}
    if block is None:
        ev[9].append("the machine-readable ```json asm-w``` block is missing or not a JSON list")
    else:
        listed = {b.get("id") for b in block if isinstance(b, dict)}
        for a in sorted(used_w - listed):
            ev[9].append(f"{a} is used but missing from the asm-w block")
        for a in sorted(listed - set(reg)):
            ev[9].append(f"{a} in the asm-w block is not registered (run status_rules.py register spec.md)")

    titles = {1: "REQ traceability", 2: "approved gaps addressed or open", 4: "research tags are kept findings",
              6: "line format", 7: "ids exist, line ids unique", 8: "labels and placement", 9: "ASM ids and stale items listed",
              15: "template sections present"}
    return [{"n": n, "severity": "blocking", "status": "fail" if ev[n] else "pass", "evidence": ev[n][:50],
             "title": titles[n]} for n in sorted(ev)]


def check_final(run_dir: Path, text: str, manifest: dict) -> list[dict]:
    ev: list[str] = []
    want = manifest.get("publication_status")
    doc = Doc(text)
    status_line = next((l for l in doc.section_text(1).splitlines() if "publication status" in l.lower()), "")
    if not want:
        ev.append("no publication status computed yet: run run_state.py report first")
    else:
        shown = re.sub(r"[`*_\s]+$", "", status_line.split(":", 1)[1] if ":" in status_line else "").strip(" `*")
        if shown != want:
            ev.append(f"Document Status shows '{shown}', computed status is '{want}'")
    hist = sorted((run_dir / "history").glob("spec-round-*.md"))
    if not hist:
        ev.append("no recorded spec version to compare with (history/ is empty)")
    else:
        prev = Doc(hist[-1].read_text(encoding="utf-8"))
        a = [l for l, (s, _) in zip(prev.lines, prev.section_of) if s != 1]
        b = [l for l, (s, _) in zip(doc.lines, doc.section_of) if s != 1]
        if a != b:
            ev.append("the final pass changed content outside Document Status")
    return [{"n": 15, "severity": "blocking", "status": "fail" if ev else "pass", "evidence": ev,
             "title": "final Document Status pass"}]


def main(argv: Sequence[str] | None = None, repo: Path | None = None, env: Mapping[str, str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args(None if argv is None else list(argv)[1:])
    repo = repo or paths.REPO_ROOT
    env = os.environ if env is None else env
    try:
        ctx = runctx.require_active_run(repo, args.run, env)
        spec = ctx.run_dir / "spec.md"
        if not spec.exists():
            raise RunError("spec.md does not exist")
        stage_key = "16" if args.final else "15"
        st = ctx.manifest["stages"].get(stage_key)
        if not st or st["status"] != "running":
            raise RunError(f"stage {stage_key} is not running")
        text = spec.read_text(encoding="utf-8")
        items = check_final(ctx.run_dir, text, ctx.manifest) if args.final else check(ctx.run_dir, text)
    except RunError as exc:
        print(json.dumps({"ok": False, "refused": str(exc)}))
        return 3
    blocking = [i["n"] for i in items if i["severity"] == "blocking" and i["status"] == "fail"]
    doc = {"schema_version": 1, "run_id": ctx.run_id, "checked_at": now_iso(), "round": args.round,
           "mode": "final" if args.final else "full", "items": items, "blocking_failures": blocking,
           "warning_failures": [], "passed": not blocking}
    schema.check("validation", doc, what="validation.json")
    fsutil.atomic_write_json(ctx.run_dir / "validation.json", doc)
    print(json.dumps({"ok": not blocking, "round": args.round, "blocking_failures": blocking,
                      "evidence": {i["n"]: i["evidence"][:5] for i in items if i["status"] == "fail"}}, indent=2,
                     ensure_ascii=False))
    return 0 if not blocking else 1


if __name__ == "__main__":
    sys.exit(main())
