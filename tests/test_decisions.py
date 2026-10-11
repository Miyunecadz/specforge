"""Phase 4: feasibility (§9.9 mapping), questions (§9.10), Checkpoint 3 (§9.11) and 13R (§9.11a)."""

from __future__ import annotations

import copy
import json

import pytest

import status_rules
import verify_citations as vc
from _lib import schema, status
from conftest import SESSION, add_subagent_event, env_for, run_cli, script_argv
from test_checkpoints import ans, answers, b64, open_and_continue, rs, sr
from test_research import fetch, finding, to_stage8, write_findings

RUN_FIELDS = {}


def to_stage11(repo):
    run_id = to_stage8(repo)
    rd = repo / "runs" / run_id
    src = fetch(repo, run_id, "https://docs.example.org/dialogs")["source_id"]
    write_findings(repo, run_id, [
        finding(1, src, "When a modal dialog opens, focus moves to an element inside the dialog."),
        finding(2, src, "When the dialog closes, focus returns to the element that invoked it",
                rec={"text": "Return focus to the Award Package button.", "rationale": "Applies the rule."})])
    add_subagent_event(repo, run_id, "web-researcher")
    assert sr(repo, "register", "findings/GAP-002.json", "--run", run_id)[0] == 0
    rc, out = rs(repo, "stage", "8", "--run", run_id, "--complete")
    assert rc == 0, out
    assert rs(repo, "stage", "9", "--run", run_id, "--start")[0] == 0
    assert run_cli(vc.main, script_argv(repo, "verify_citations", "--run", run_id), repo, env_for())[0] == 0
    assert sr(repo, "verification", "--run", run_id, "--from", "citations")[0] == 0
    assert rs(repo, "stage", "9", "--run", run_id, "--complete")[0] == 0
    assert rs(repo, "stage", "10", "--run", run_id, "--start")[0] == 0
    (rd / "verified_findings.json").write_text(json.dumps({"schema_version": 1, "run_id": run_id,
        "kept": [{"finding_id": "F-GAP-002-01", "notes": "ok", "limitations": []}],
        "dropped": [{"finding_id": "F-GAP-002-02", "reasons": [{"code": "adds_assumptions", "explanation": "x"}]}],
        "contradictions": [], "proposed_status_changes": []}))
    assert sr(repo, "verification", "--run", run_id, "--from", "semantic")[0] == 0
    add_subagent_event(repo, run_id, "source-verifier")
    assert rs(repo, "stage", "10", "--run", run_id, "--complete")[0] == 0
    assert rs(repo, "stage", "11", "--run", run_id, "--start")[0] == 0
    return run_id


def fea(i, cls, related, evidence=True):
    prov, kind = {"required_by_customer": ("customer_requirement", "finding"),
                  "supported_by_evidence": ("research_evidence", "finding"),
                  "recommended_for_consideration": ("inference", "recommendation"),
                  "undecided": ("inference", "finding")}[cls]
    return {"id": f"FEA-{i:03d}", "title": f"Item {i}", "area": "roles_and_permissions", "description": "d",
            "classification": cls, "related_ids": related,
            "evidence_refs": [{"artifact": "inventory.json", "locator": "SCR-001"}] if evidence else [],
            "uncertainties": [], "provenance": prov, "kind": kind}


def feas_doc(run_id, items):
    return {"schema_version": 1, "run_id": run_id, "items": items, "new_unknowns": [],
            "assumptions": [{"id": "ASM-F-001", "text": "t", "why": "w", "impact": "i", "to_confirm": "c",
                             "provenance": "assumption", "kind": "assumption"}],
            "proposed_status_changes": [], "inspected_documents": []}


GOOD = [fea(1, "required_by_customer", ["REQ-001"]), fea(2, "supported_by_evidence", ["F-GAP-002-01"]),
        fea(3, "recommended_for_consideration", ["GAP-002"]), fea(4, "undecided", ["REQ-002"])]


# --------------------------------------------------------------------------- schema mapping


def test_schema_accepts_correct_mapping():
    assert schema.errors("feasibility", feas_doc("20261011-120000-abcdef", GOOD)) == []


@pytest.mark.parametrize("mutate", [
    lambda i: i.update(provenance="inference"),                        # required_by_customer with wrong provenance
    lambda i: i.update(kind="recommendation"),
    lambda i: i.update(related_ids=["GAP-002"]),                      # no REQ
    lambda i: i.update(classification="maybe"),
    lambda i: i.pop("classification"),                                 # unclassified
    lambda i: i.update(approval="approved"),                           # status field
])
def test_schema_rejects_bad_required_by_customer(mutate):
    items = copy.deepcopy(GOOD)
    mutate(items[0])
    assert schema.errors("feasibility", feas_doc("20261011-120000-abcdef", items))


def test_schema_rejects_bad_other_classes():
    items = copy.deepcopy(GOOD)
    items[1]["related_ids"] = ["REQ-001"]          # supported_by_evidence without a finding
    assert schema.errors("feasibility", feas_doc("20261011-120000-abcdef", items))
    items = copy.deepcopy(GOOD)
    items[2]["evidence_refs"] = []                  # recommendation without evidence
    assert schema.errors("feasibility", feas_doc("20261011-120000-abcdef", items))
    items = copy.deepcopy(GOOD)
    items[2]["kind"] = "finding"                    # recommended_for_consideration must be a recommendation
    assert schema.errors("feasibility", feas_doc("20261011-120000-abcdef", items))


# --------------------------------------------------------------------------- register + labels


@pytest.fixture
def s11(repo):
    return repo, to_stage11(repo)


def write_feas(repo, run_id, items):
    (repo / "runs" / run_id / "feasibility.json").write_text(json.dumps(feas_doc(run_id, items)))


def test_register_feasibility_and_labels(s11):
    repo, run_id = s11
    write_feas(repo, run_id, GOOD)
    assert sr(repo, "register", "feasibility.json", "--run", run_id)[0] == 0
    add_subagent_event(repo, run_id, "feasibility-analyst")
    assert rs(repo, "stage", "11", "--run", run_id, "--complete")[0] == 0
    assert sr(repo, "labels", "--run", run_id)[0] == 0
    lab = json.loads((repo / "runs" / run_id / "status_labels.json").read_text())["items"]
    assert [lab[f"FEA-00{i}"]["label"] for i in range(1, 5)] == \
        ["Explicit", "Research-supported", "Recommended (awaiting approval)", "Unknown"]
    reg = json.loads((repo / "runs" / run_id / "status_registry.json").read_text())["items"]
    assert reg["FEA-004"]["issues"] == ["unknown"] and reg["ASM-F-001"]["approval"] == "not_reviewed"


@pytest.mark.parametrize("bad,msg", [
    (fea(1, "required_by_customer", ["REQ-009"]), "no live REQ"),
    (fea(1, "supported_by_evidence", ["F-GAP-002-02"]), "verification kept"),    # dropped finding
    (fea(1, "recommended_for_consideration", ["GAP-099"]), "unknown item GAP-099"),
])
def test_register_enforces_references(s11, bad, msg):
    repo, run_id = s11
    write_feas(repo, run_id, [bad])
    rc, out = sr(repo, "register", "feasibility.json", "--run", run_id)
    assert rc == 1 and msg in out["error"]


def test_required_by_customer_cannot_cite_rejected_requirement(s11):
    repo, run_id = s11
    rd = repo / "runs" / run_id
    st = status_rules.load_state(rd, run_id)
    st.registry["items"]["REQ-003"]["approval"] = "rejected"   # simulate an earlier rejection (direct, test-only)
    rd.joinpath("status_registry.json").write_text(json.dumps(st.registry))
    write_feas(repo, run_id, [fea(1, "required_by_customer", ["REQ-003"])])
    assert sr(repo, "register", "feasibility.json", "--run", run_id)[0] == 1


# --------------------------------------------------------------------------- questions and checkpoint 3


def q(i, prio="important", rec=None, affected=("REQ-001",)):
    return {"id": f"Q-{i:03d}", "question": f"Question {i}?", "why_it_matters": "w", "affected_ids": list(affected),
            "topic_keywords": ["award"], "options": [{"option": "A", "trade_offs": "a"}, {"option": "B", "trade_offs": "b"}],
            "recommendation": rec, "blocking": False, "priority": prio}


def to_stage12(repo):
    run_id = to_stage11(repo)
    write_feas(repo, run_id, GOOD)
    sr(repo, "register", "feasibility.json", "--run", run_id)
    add_subagent_event(repo, run_id, "feasibility-analyst")
    assert rs(repo, "stage", "11", "--run", run_id, "--complete")[0] == 0
    assert rs(repo, "stage", "12", "--run", run_id, "--start")[0] == 0
    return run_id


def write_qs(repo, run_id, qs):
    (repo / "runs" / run_id / "questions.json").write_text(json.dumps(
        {"schema_version": 1, "run_id": run_id, "questions": qs, "implementation_details": []}))


@pytest.mark.parametrize("qs,msg", [
    ([q(i) for i in range(1, 12)], "exceed max_customer_questions"),
    ([q(1, rec={"option": "A", "finding_ids": ["F-GAP-002-02"], "rationale": "r"})], "not kept"),
    ([q(1, rec={"option": "C", "finding_ids": ["F-GAP-002-01"], "rationale": "r"})], "not listed"),
    ([q(1, "optional"), q(2, "critical")], "ordered by priority"),
    ([q(2)], "Q-001, Q-002"),
    ([q(1, affected=("REQ-042",))], "unknown item REQ-042"),
])
def test_question_checks(repo, qs, msg):
    run_id = to_stage12(repo)
    write_qs(repo, run_id, qs)
    add_subagent_event(repo, run_id, "question-generator")
    rc, out = rs(repo, "stage", "12", "--run", run_id, "--complete")
    assert rc == 1 and any(msg in e for e in out["errors"]), out


def test_checkpoint_3_records_answers_and_allows_open_questions(repo):
    run_id = to_stage12(repo)
    rd = repo / "runs" / run_id
    write_qs(repo, run_id, [q(1, "critical", rec={"option": "A", "finding_ids": ["F-GAP-002-01"], "rationale": "r"},
                              affected=("FEA-003",)), q(2)])
    add_subagent_event(repo, run_id, "question-generator")
    assert rs(repo, "stage", "12", "--run", run_id, "--complete")[0] == 0
    assert rs(repo, "stage", "13", "--run", run_id, "--start")[0] == 0
    open_and_continue(repo, run_id, "3")
    bad = answers("3", [ans("Option A.", [], question_ids=["Q-009"])])
    assert sr(repo, "decide", "--run", run_id, "--checkpoint", "3", "--answers-b64", b64(bad))[0] == 1
    a = answers("3", [ans("Go with option A for Q-001.", [{"type": "approve", "item_id": "FEA-003"}],
                          question_ids=["Q-001"], affected=["FEA-003", "Q-001"]),
                      ans("Leave Q-002 open for now.", [{"type": "leave_open"}], question_ids=["Q-002"])])
    assert sr(repo, "decide", "--run", run_id, "--checkpoint", "3", "--answers-b64", b64(a))[0] == 0
    assert rs(repo, "stage", "13", "--run", run_id, "--complete")[0] == 0
    sr(repo, "labels", "--run", run_id)
    lab = json.loads((rd / "status_labels.json").read_text())
    assert lab["items"]["FEA-003"]["label"].startswith("Approved: DEC-") and lab["stale_approved"] == []
    rc, out = rs(repo, "stage", "13R", "--run", run_id, "--start")
    assert rc == 3 and "no" in out["refused"]          # 13R only when approved items are stale
    import run_state
    manifest = json.loads((rd / "run_manifest.json").read_text())
    assert run_state._prior_stages_done(manifest, "14") == []   # an unneeded 13R does not block Stage 14


# --------------------------------------------------------------------------- 13R


def make_stale(repo, run_id, item_id, reason):
    rd = repo / "runs" / run_id
    st = status_rules.load_state(rd, run_id)
    status.apply_stale(st, item_id, reason)
    status_rules.save_state(rd, st, decisions_changed=False)   # the owning script's own write path


def test_reconfirmation_path(repo):
    run_id = to_stage12(repo)
    rd = repo / "runs" / run_id
    write_qs(repo, run_id, [q(1)])
    add_subagent_event(repo, run_id, "question-generator")
    rs(repo, "stage", "12", "--run", run_id, "--complete")
    rs(repo, "stage", "13", "--run", run_id, "--start")
    open_and_continue(repo, run_id, "3")
    sr(repo, "decide", "--run", run_id, "--checkpoint", "3", "--answers-b64",
       b64(answers("3", [ans("Approve FEA-003 and FEA-001.", [{"type": "approve", "item_id": "FEA-003"},
                                                              {"type": "approve", "item_id": "FEA-001"}])])))
    assert rs(repo, "stage", "13", "--run", run_id, "--complete")[0] == 0
    make_stale(repo, run_id, "FEA-003", "REQ-002 changed after Checkpoint 3")
    make_stale(repo, run_id, "FEA-001", "REQ-001 changed after Checkpoint 3")
    make_stale(repo, run_id, "ASM-F-001", "REQ-002 changed after Checkpoint 3")   # unapproved: superseded
    assert rs(repo, "verify", "--run", run_id)[0] == 0                         # legitimate owner writes
    sr(repo, "labels", "--run", run_id)
    lab = json.loads((rd / "status_labels.json").read_text())
    assert lab["stale_approved"] == ["FEA-001", "FEA-003"]
    assert lab["items"]["FEA-003"]["label"].startswith("Stale: re-confirm (DEC-")
    assert lab["items"]["ASM-F-001"]["placement"] == "decisions_log"
    assert rs(repo, "stage", "13R", "--run", run_id, "--skip", "--reason", "x")[0] == 3
    assert rs(repo, "stage", "13R", "--run", run_id, "--start")[0] == 0
    open_and_continue(repo, run_id, "13R")
    a = answers("13R", [ans("Keep FEA-003 as approved.", [{"type": "reconfirm", "item_id": "FEA-003"}]),
                        ans("Leave FEA-001 open.", [{"type": "leave_open", "item_id": "FEA-001"}])])
    assert sr(repo, "decide", "--run", run_id, "--checkpoint", "13R", "--answers-b64", b64(a))[0] == 0
    assert rs(repo, "stage", "13R", "--run", run_id, "--complete")[0] == 0
    reg = json.loads((rd / "status_registry.json").read_text())["items"]
    assert not reg["FEA-003"]["stale"] and reg["FEA-003"]["approval"] == "approved"
    assert reg["FEA-001"]["stale"] and reg["FEA-001"]["approval"] == "approved"   # left open: stays Stale
    sr(repo, "labels", "--run", run_id)
    assert json.loads((rd / "status_labels.json").read_text())["stale_approved"] == ["FEA-001"]
