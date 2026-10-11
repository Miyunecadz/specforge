"""Phase 5: check_spec.py, ASM-W registration, revision rounds, publication status, final pass, post-15 13R."""

from __future__ import annotations

import json

import pytest

import check_spec as cs
import status_rules
from _lib import status
from conftest import SESSION, add_subagent_event, env_for, run_cli, script_argv
from test_checkpoints import ans, answers, b64, open_and_continue, rs, sr
from test_decisions import to_stage12, write_qs, q


def to_stage14(repo):
    run_id = to_stage12(repo)
    write_qs(repo, run_id, [q(1, "critical", affected=("FEA-004",))])
    add_subagent_event(repo, run_id, "question-generator")
    assert rs(repo, "stage", "12", "--run", run_id, "--complete")[0] == 0
    assert rs(repo, "stage", "13", "--run", run_id, "--start")[0] == 0
    open_and_continue(repo, run_id, "3")
    assert sr(repo, "decide", "--run", run_id, "--checkpoint", "3", "--answers-b64",
              b64(answers("3", [ans("Approve the audit recommendation; reject finance export.",
                                    [{"type": "approve", "item_id": "FEA-003"}, {"type": "reject", "item_id": "REQ-003"}],
                                    question_ids=["Q-001"])])))[0] == 0
    assert rs(repo, "stage", "13", "--run", run_id, "--complete")[0] == 0
    assert sr(repo, "labels", "--run", run_id)[0] == 0
    assert rs(repo, "stage", "14", "--run", run_id, "--start")[0] == 0
    return run_id


def L(rd, i):
    return json.loads((rd / "status_labels.json").read_text())["items"][i]["label"]


def good_spec(rd, run_id, asm_w=True, status_line="pending final pass"):
    reg = json.loads((rd / "status_registry.json").read_text())["items"]
    reqs = sorted(i for i in reg if i.startswith("REQ-"))
    gaps = sorted(i for i, it in reg.items() if i.startswith("GAP-"))
    trace = "\n".join(f"| {r} | requirement | {'out of scope' if reg[r]['approval'] == 'rejected' else 'addressed'} | {L(rd, r)} | - |"
                      for r in reqs)
    gap_rows = "\n".join(f"| {g} | gap | {reg[g]['approval']} | - | - | {'addressed' if reg[g]['approval'] == 'approved' else 'rejected'} | - |"
                         for g in gaps)
    asm_rows = "\n".join(f"| {a} | assumption | w | - | i | no | - | open |" for a in sorted(i for i in reg if i.startswith("ASM-")))
    block = '[{"id": "ASM-W-001", "text": "Awards are made one at a time.", "why": "not stated", "impact": "concurrency", "to_confirm": "Can two managers award at once?"}]' if asm_w else "[]"
    w_row = "| ASM-W-001 | Awards are made one at a time. | concurrency | FEA-004 | high | no | Procurement | open |" if asm_w else ""
    return f"""# Award packages: Feature Specification

## 1. Document Status

- Run ID: {run_id}
- Publication status: {status_line}

## 2. Executive Summary

Procurement staff award supplier packages.

## 3. Goals and Scope

### Goals

### In Scope

### Out of Scope / Rejected

- [Customer: REQ-003 · {L(rd, 'REQ-003')}] Finance export.

### Deferred

## 4. Users and Roles

## 5. Existing Mockup Coverage

## 6. Requirements Traceability

| REQ | Requirement | Treatment | Label | References |
|---|---|---|---|---|
{trace}

## 7. Gaps Identified

| GAP | Gap | Approval | Path | Priority | Status | Rationale |
|---|---|---|---|---|---|---|
{gap_rows}

## 8. Functional Requirements

### Awarding

#### Confirmed requirements

- **FR-001** Package managers can award a supplier package. [Customer: REQ-001 · {L(rd, 'REQ-001')}] [Mockup: SCR-001]

#### Recommendations awaiting approval

- **FR-002** Record who awarded a package and when. [Inferred: FEA-003 · {L(rd, 'FEA-003')}]

#### Acceptance criteria

- **AC-001** Given a manager, when they award, then the package shows the supplier. [Customer: REQ-001 · {L(rd, 'REQ-001')}]
- **AC-002** (draft) Given an open dialog, when it opens, then focus moves inside it. [Research: F-GAP-002-01 · {L(rd, 'F-GAP-002-01')}]

## 9. State Transitions and Edge Cases

### Package lifecycle

| State | Event | Next state | Who can trigger | Provenance |
|---|---|---|---|---|
| Open | Award | Awarded | Procurement | [Customer: REQ-001 · {L(rd, 'REQ-001')}] |

## 10. Non-Functional Requirements

- **NFR-001** (Assumption ASM-W-001 applies) Awards are processed one at a time. [Inferred: FEA-004 · {L(rd, 'FEA-004')}]

## 11. Data Model and Business Rules

- **BR-001** An awarded package is read-only. [Customer: REQ-002 · {L(rd, 'REQ-002')}]

## 12. Screens and User Flows

## 13. Integrations and Dependencies

## 14. Security, Privacy, and Error Handling

## 15. Decisions Log

| DEC | Checkpoint | Decided | Verbatim answer | Interpretation | Items affected | Supersedes / superseded by |
|---|---|---|---|---|---|---|

## 16. Open Questions and Assumptions

| ID | Text | Why it matters | Related items | Impact | Blocking | Owner | Status |
|---|---|---|---|---|---|---|---|
{asm_rows}
{w_row}

## 17. Research Findings and Recommendations

- [Research: F-GAP-002-01 · {L(rd, 'F-GAP-002-01')}] Focus moves into an opened dialog.

## 18. Sources

### Limitations

- F-GAP-002-02 was dropped: adds assumptions.

```json asm-w
{block}
```
"""


@pytest.fixture
def s14(repo):
    run_id = to_stage14(repo)
    rd = repo / "runs" / run_id
    (rd / "spec.md").write_text(good_spec(rd, run_id))
    assert sr(repo, "register", "spec.md", "--run", run_id)[0] == 0
    assert sr(repo, "labels", "--run", run_id)[0] == 0
    return repo, run_id, rd


def run_checks(rd, text):
    return {i["n"]: i for i in cs.check(rd, text)}


def test_good_spec_passes_all_code_checks(s14):
    repo, run_id, rd = s14
    res = run_checks(rd, (rd / "spec.md").read_text())
    assert all(i["status"] == "pass" for i in res.values()), {n: i["evidence"] for n, i in res.items() if i["status"] == "fail"}
    reg = json.loads((rd / "status_registry.json").read_text())["items"]
    assert reg["ASM-W-001"]["approval"] == "not_reviewed" and reg["ASM-W-001"]["source_artifact"] == "spec.md"
    assert L(rd, "ASM-W-001") == "Assumption"


@pytest.mark.parametrize("mutate,item", [
    (lambda t: t.replace("## 13. Integrations and Dependencies", "## 13. Integrations"), 15),
    (lambda t: t.replace("### Deferred", "### Later"), 15),
    (lambda t: t.replace("- **FR-001** Package", "- **FR-1** Package"), 6),
    (lambda t: t.replace("[Customer: REQ-001 · Explicit] [Mockup: SCR-001]", "[Customer: REQ-001] [Mockup: SCR-001]"), 6),
    (lambda t: t.replace("[Customer: REQ-001 · Explicit] [Mockup", "[Customer: REQ-001 · Approved: DEC-001] [Mockup"), 8),
    (lambda t: t.replace("- **AC-002** (draft) Given", "- **AC-002** Given"), 6),
    (lambda t: t.replace("- **AC-001** Given", "- **AC-001** (draft) Given"), 6),
    (lambda t: t.replace("- **FR-002** Record", "- **FR-002** (draft) Record"), 6),
    (lambda t: t.replace("#### Confirmed requirements\n", "#### Confirmed requirements\n\n- **FR-009** Export awards. [Customer: REQ-003 · Rejected: DEC-003]\n"), 8),
    (lambda t: t.replace("#### Confirmed requirements\n", "#### Confirmed requirements\n\n- **FR-009** Return focus in 200 ms. [Research: F-GAP-002-02 · Dropped]\n"), 4),
    (lambda t: t.replace("[Mockup: SCR-001]", "[Mockup: SCR-099]"), 7),
    (lambda t: t.replace("- **BR-001**", "- **FR-001**"), 7),
    (lambda t: t.replace("[Inferred: FEA-003", "[Research: FEA-003"), 6),
    (lambda t: t.replace("| Open | Award | Awarded | Procurement | [Customer: REQ-001 · Explicit] |", "| Open | Award | Awarded | Procurement | Customer said so |"), 6),
])
def test_each_code_check_catches_its_defect(s14, mutate, item):
    repo, run_id, rd = s14
    text = mutate((rd / "spec.md").read_text())
    res = run_checks(rd, text)
    assert res[item]["status"] == "fail", {n: i["evidence"] for n, i in res.items()}


def test_traceability_gaps_open_questions_and_asm_block(s14):
    repo, run_id, rd = s14
    base = (rd / "spec.md").read_text()
    t = "\n".join(l for l in base.splitlines() if not l.startswith("| REQ-002 |"))
    assert run_checks(rd, t)[1]["status"] == "fail"
    t = base.replace("| addressed |", "| done |")
    assert run_checks(rd, t)[1]["status"] == "fail"
    t = "\n".join(l for l in base.splitlines() if not l.startswith("| GAP-002 |"))
    assert run_checks(rd, t)[2]["status"] == "fail"
    t = "\n".join(l for l in base.splitlines() if not l.startswith("| ASM-W-001 |"))
    assert run_checks(rd, t)[9]["status"] == "fail"
    t = base.replace('"id": "ASM-W-001"', '"id": "ASM-W-002"')
    assert run_checks(rd, t)[9]["status"] == "fail"           # used id missing from block / unregistered
    t = base.replace("```json asm-w", "```json")
    assert run_checks(rd, t)[9]["status"] == "fail"


def test_stale_item_must_be_in_open_questions(s14):
    repo, run_id, rd = s14
    st = status_rules.load_state(rd, run_id)
    status.apply_stale(st, "FEA-003", "REQ-001 changed")
    status_rules.save_state(rd, st, decisions_changed=False)
    sr(repo, "labels", "--run", run_id)
    text = good_spec(rd, run_id).replace("| ASM-F-001 |", "| ASM-F-001 |")
    res = run_checks(rd, "\n".join(l for l in text.splitlines() if "FEA-003" not in l or "**FR-002**" in l))
    assert res[9]["status"] == "fail"


def test_register_spec_rejects_bad_block(s14):
    repo, run_id, rd = s14
    (rd / "spec.md").write_text(good_spec(rd, run_id).replace('"to_confirm": "Can two managers award at once?"', '"to_confirm": ""'))
    assert sr(repo, "register", "spec.md", "--run", run_id)[0] == 1
    (rd / "spec.md").write_text(good_spec(rd, run_id).replace("```json asm-w\n[", "```json asm-w\n{").replace("}]\n```", "}\n```"))
    assert sr(repo, "register", "spec.md", "--run", run_id)[0] == 1


# --------------------------------------------------------------------------- stage 14-16 flow


def cs_run(repo, run_id, *extra):
    return run_cli(cs.main, script_argv(repo, "check_spec", "--run", run_id, *extra), repo, env_for())


def review(rd, run_id, rnd, passed=True, warn_fail=False):
    items = [{"n": n, "severity": "blocking", "status": "pass" if passed else "fail", "evidence": ["e"]} for n in (3, 5, 10, 11, 12, 13, 14)]
    items += [{"n": n, "severity": "warning", "status": "fail" if warn_fail and n == 16 else "pass", "evidence": ["e"]} for n in range(16, 22)]
    (rd / "review.json").write_text(json.dumps({"schema_version": 1, "run_id": run_id, "round": rnd, "passed": passed, "items": items,
        "fixes": [] if passed else [{"location": "8", "problem": "p", "required_change": "c", "item": 5}],
        "unresolved_issues": [] if passed else ["claim unsupported"]}))


def to_stage15(repo, s14):
    repo, run_id, rd = s14
    add_subagent_event(repo, run_id, "doc-writer")
    assert rs(repo, "stage", "14", "--run", run_id, "--complete")[0] == 0
    assert rs(repo, "stage", "15", "--run", run_id, "--start")[0] == 0
    return run_id, rd


def finish(repo, run_id, rd):
    """Stage 16 with the final Document Status pass."""
    assert rs(repo, "stage", "16", "--run", run_id, "--start")[0] == 0
    rc, out = rs(repo, "report", "--run", run_id)
    assert rc == 0
    status_ = out["publication_status"]
    text = (rd / "spec.md").read_text().replace("Publication status: pending final pass", f"Publication status: {status_}")
    (rd / "spec.md").write_text(text)
    add_subagent_event(repo, run_id, "doc-writer")
    assert cs_run(repo, run_id, "--final", "--round", "9")[0] == 0
    assert rs(repo, "record-revision", "--run", run_id, "--final")[0] == 0
    assert rs(repo, "stage", "16", "--run", run_id, "--complete")[0] == 0
    assert rs(repo, "verify", "--run", run_id)[0] == 0
    assert rs(repo, "end", "--run", run_id)[0] == 0
    return status_


def test_clean_pass_is_validated(s14):
    repo = s14[0]
    run_id, rd = to_stage15(repo, s14)
    assert cs_run(repo, run_id, "--round", "1")[0] == 0
    review(rd, run_id, 1)
    add_subagent_event(repo, run_id, "doc-reviewer")
    assert rs(repo, "stage", "15", "--run", run_id, "--complete")[0] == 0
    assert finish(repo, run_id, rd) == "validated"
    summary = json.loads((rd / "run_summary.json").read_text())
    assert summary["publication_status"] == "validated" and summary["counts"]["findings_by_verification"] == {"kept": 1, "dropped": 1}


def test_review_warning_gives_validated_with_warnings(s14):
    repo = s14[0]
    run_id, rd = to_stage15(repo, s14)
    cs_run(repo, run_id, "--round", "1")
    review(rd, run_id, 1, warn_fail=True)
    add_subagent_event(repo, run_id, "doc-reviewer")
    assert rs(repo, "stage", "15", "--run", run_id, "--complete")[0] == 0
    assert finish(repo, run_id, rd) == "validated_with_warnings"


def test_failures_require_two_revision_rounds_then_not_fully_validated(s14):
    repo = s14[0]
    run_id, rd = to_stage15(repo, s14)
    cs_run(repo, run_id, "--round", "1")
    review(rd, run_id, 1, passed=False)
    add_subagent_event(repo, run_id, "doc-reviewer")
    rc, out = rs(repo, "stage", "15", "--run", run_id, "--complete")
    assert rc == 1 and any("revision rounds" in e for e in out["errors"])
    # a spec change without a doc-writer invocation is refused
    (rd / "spec.md").write_text((rd / "spec.md").read_text().replace("Procurement staff", "Procurement team"))
    rc, out = rs(repo, "record-revision", "--run", run_id)
    assert rc == 3 and "doc-writer" in out["refused"]
    for rnd in (2, 3):
        add_subagent_event(repo, run_id, "doc-writer")
        assert rs(repo, "record-revision", "--run", run_id)[0] == 0
        assert sr(repo, "register", "spec.md", "--run", run_id)[0] == 0
        cs_run(repo, run_id, "--round", str(rnd))
        review(rd, run_id, rnd, passed=False)
        add_subagent_event(repo, run_id, "doc-reviewer")
    assert rs(repo, "stage", "15", "--run", run_id, "--complete")[0] == 0   # rounds exhausted: may finish
    assert (rd / "history/spec-round-01.md").exists() and (rd / "history/spec-round-02.md").exists()
    assert rs(repo, "verify", "--run", run_id)[0] == 0
    assert finish(repo, run_id, rd) == "not_fully_validated"


def test_unrecorded_spec_change_is_tamper(s14):
    repo = s14[0]
    run_id, rd = to_stage15(repo, s14)
    (rd / "spec.md").write_text((rd / "spec.md").read_text() + "\nedited\n")
    rc, out = rs(repo, "verify", "--run", run_id)
    assert rc == 4 and any(t["file"].endswith("spec.md") for t in out["tamper"])


def test_final_pass_may_only_change_document_status(s14):
    repo = s14[0]
    run_id, rd = to_stage15(repo, s14)
    cs_run(repo, run_id, "--round", "1")
    review(rd, run_id, 1)
    add_subagent_event(repo, run_id, "doc-reviewer")
    rs(repo, "stage", "15", "--run", run_id, "--complete")
    add_subagent_event(repo, run_id, "doc-writer")
    assert rs(repo, "record-revision", "--run", run_id)[0] == 3   # not in stage 15/16 any more
    rs(repo, "stage", "16", "--run", run_id, "--start")
    rs(repo, "report", "--run", run_id)
    text = (rd / "spec.md").read_text().replace("Publication status: pending final pass", "Publication status: validated")
    (rd / "spec.md").write_text(text.replace("Procurement staff award", "Everyone awards"))
    rc, out = cs_run(repo, run_id, "--final")
    assert rc == 1 and "outside Document Status" in json.dumps(out)
    (rd / "spec.md").write_text(text.replace("validated", "validated_with_warnings", 1))
    assert cs_run(repo, run_id, "--final")[0] == 1                 # wrong status shown
    (rd / "spec.md").write_text(text)
    assert cs_run(repo, run_id, "--final")[0] == 0


def test_fixture_mode_is_always_eval_only(repo):
    import run_state
    from _lib import runctx
    run_id = to_stage14(repo)
    ctx = runctx.require_active_run(repo, run_id, env_for())
    ctx.mode = runctx.modes.Mode("fixture", repo / "evals/fixtures/case-a")
    status_, reasons = run_state._publication_status(ctx)
    assert status_ == "eval_only" and "fixture mode" in reasons[0]


def test_post_review_reconfirmation_runs_once_and_reruns_14_15(s14):
    repo = s14[0]
    run_id, rd = to_stage15(repo, s14)
    cs_run(repo, run_id, "--round", "1")
    review(rd, run_id, 1)
    add_subagent_event(repo, run_id, "doc-reviewer")
    assert rs(repo, "stage", "15", "--run", run_id, "--complete")[0] == 0
    st = status_rules.load_state(rd, run_id)
    status.apply_stale(st, "FEA-003", "REQ-002 changed during review")
    status_rules.save_state(rd, st, decisions_changed=False)
    assert rs(repo, "stage", "16", "--run", run_id, "--start")[0] == 0
    assert rs(repo, "stage", "16", "--run", run_id, "--fail", "--reason", "stale items appeared after review")[0] == 0
    assert rs(repo, "stage", "13R", "--run", run_id, "--start")[0] == 0
    open_and_continue(repo, run_id, "13R")
    assert sr(repo, "decide", "--run", run_id, "--checkpoint", "13R", "--answers-b64",
              b64(answers("13R", [ans("Keep the audit item.", [{"type": "reconfirm", "item_id": "FEA-003"}])])))[0] == 0
    assert rs(repo, "stage", "13R", "--run", run_id, "--complete")[0] == 0
    m = json.loads((rd / "run_manifest.json").read_text())
    assert m["stages"]["14"]["status"] == "stale" and m["stages"]["15"]["status"] == "stale"
    assert rs(repo, "stage", "14", "--run", run_id, "--start")[0] == 0           # re-run once
    add_subagent_event(repo, run_id, "doc-writer")
    sr(repo, "register", "spec.md", "--run", run_id)
    assert rs(repo, "stage", "14", "--run", run_id, "--complete")[0] == 0
    assert rs(repo, "stage", "15", "--run", run_id, "--start")[0] == 0
    cs_run(repo, run_id, "--round", "1")
    review(rd, run_id, 1)
    add_subagent_event(repo, run_id, "doc-reviewer")
    assert rs(repo, "stage", "15", "--run", run_id, "--complete")[0] == 0
    # more items go stale: a second post-review re-confirmation is refused; they stay Stale
    st = status_rules.load_state(rd, run_id)
    status.apply_stale(st, "FEA-003", "yet another change")
    status_rules.save_state(rd, st, decisions_changed=False)
    rc, out = rs(repo, "stage", "13R", "--run", run_id, "--start")
    assert rc == 3 and "already ran once" in out["refused"]
    sr(repo, "labels", "--run", run_id)
    assert finish_with_stale(repo, run_id, rd) == "validated_with_warnings"


def finish_with_stale(repo, run_id, rd):
    """Stage 16 when stale items remain: the spec must list them in Open Questions (doc-writer final pass)."""
    rs(repo, "stage", "16", "--run", run_id, "--start")
    rc, out = rs(repo, "report", "--run", run_id)
    return out["publication_status"]
