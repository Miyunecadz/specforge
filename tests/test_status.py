"""Status model (BUILD_SPEC §6): every transition row, stale, verification, placement and label rules."""

from __future__ import annotations

import itertools

import pytest

from _lib import status as S

APPROVALS = S.APPROVALS


def state(**items):
    reg = {"schema_version": 1, "run_id": "20261011-120000-abcdef", "items": {}, "registered_artifacts": {}}
    st = S.State(reg, {"schema_version": 1, "run_id": reg["run_id"], "decisions": []})
    for iid, kw in items.items():
        it = S.new_item(iid, kw.get("kind", "requirement"), kw.get("provenance", "customer_requirement"),
                        "requirements.json", kw.get("dec"))
        it.update({k: v for k, v in kw.items() if k not in ("kind", "provenance", "dec")})
        reg["items"][iid] = it
    return st


VALID = sorted(S.TRANSITIONS)
INVALID = [(a, b) for a, b in itertools.product(APPROVALS, APPROVALS) if a != b and (a, b) not in S.TRANSITIONS]


@pytest.mark.parametrize("frm,to", VALID)
def test_every_valid_transition_with_its_requirement(frm, to):
    need = S.TRANSITIONS[(frm, to)]
    st = state(**{"REQ-001": {"approval": frm}})
    kwargs = {"dec": "DEC-001"} if need in ("dec",) else {"reason": "r"} if need == "reason" else {"stale_reason": "x"}
    S.transition(st, "REQ-001", to, **kwargs)
    assert st.item("REQ-001")["approval"] == to
    assert st.changes[0].field == "approval" and (st.changes[0].old, st.changes[0].new) == (frm, to)


@pytest.mark.parametrize("frm,to", [k for k, v in S.TRANSITIONS.items() if v == "dec"])
def test_dec_required(frm, to):
    st = state(**{"REQ-001": {"approval": frm}})
    with pytest.raises(S.StatusError, match="requires a decision"):
        S.transition(st, "REQ-001", to, reason="no dec")


@pytest.mark.parametrize("frm,to", [k for k, v in S.TRANSITIONS.items() if v == "dec_or_stale"])
def test_dec_or_stale_required(frm, to):
    st = state(**{"REQ-001": {"approval": frm}})
    with pytest.raises(S.StatusError):
        S.transition(st, "REQ-001", to, reason="neither")
    S.transition(st, "REQ-001", to, stale_reason="REQ-002 changed")
    assert st.item("REQ-001")["approval"] == "superseded"


@pytest.mark.parametrize("frm,to", [k for k, v in S.TRANSITIONS.items() if v == "reason"])
def test_reason_required(frm, to):
    st = state(**{"REQ-001": {"approval": frm}})
    with pytest.raises(S.StatusError):
        S.transition(st, "REQ-001", to)


@pytest.mark.parametrize("frm,to", INVALID)
def test_every_invalid_transition_is_rejected(frm, to):
    st = state(**{"REQ-001": {"approval": frm}})
    with pytest.raises(S.StatusError, match="not a valid transition"):
        S.transition(st, "REQ-001", to, dec="DEC-001", reason="r", stale_reason="s")


def test_superseded_is_terminal():
    for to in APPROVALS:
        if to != "superseded":
            assert ("superseded", to) not in S.TRANSITIONS


def test_initial_approval():
    assert S.new_item("REQ-001", "requirement", "customer_requirement", "r")["approval"] == "not_reviewed"
    assert S.new_item("REQ-009", "requirement", "user_decision", "d", "DEC-001")["approval"] == "approved"
    with pytest.raises(S.StatusError):
        S.new_item("REQ-009", "requirement", "user_decision", "d")
    for prov in ("mockup_observation", "research_evidence", "inference", "assumption"):
        assert S.new_item("GAP-001", "gap", prov, "g")["approval"] == "not_reviewed"


def test_duplicate_ids_rejected_across_artifacts_but_reregistration_is_idempotent():
    st = state()
    S.register_item(st, S.new_item("REQ-001", "requirement", "customer_requirement", "requirements.json"))
    S.register_item(st, S.new_item("REQ-001", "requirement", "customer_requirement", "requirements.json"))
    with pytest.raises(S.StatusError, match="duplicate"):
        S.register_item(st, S.new_item("REQ-001", "gap", "inference", "gaps.json"))


# --------------------------------------------------------------------------- stale


def test_approved_stale_stays_approved_and_unapproved_stale_is_superseded():
    st = state(**{"REQ-001": {"approval": "approved", "decision_ids": ["DEC-001"]}, "REQ-002": {}, "REQ-003": {"approval": "deferred"}})
    for i in ("REQ-001", "REQ-002", "REQ-003"):
        S.apply_stale(st, i, "requirements changed: REQ-007")
    assert st.item("REQ-001")["approval"] == "approved" and st.item("REQ-001")["stale"]
    assert st.item("REQ-002")["approval"] == "superseded"
    assert st.item("REQ-003")["approval"] == "superseded"
    assert any(c.stale_reason == "requirements changed: REQ-007" for c in st.changes if c.field == "approval")


def answer(actions, verbatim="yes", affected=()):
    return {"presented": "Q", "verbatim": verbatim, "interpretation": "I", "affected_ids": list(affected), "actions": actions}


def test_only_a_decision_clears_stale():
    st = state(**{"REQ-001": {"approval": "approved", "decision_ids": ["DEC-001"], "stale": True, "stale_reason": "x"}})
    st.decisions["decisions"].append({"id": "DEC-001"})
    S.record_decision(st, checkpoint="13R", source="user", timestamp="t", answer=answer([{"type": "leave_open", "item_id": "REQ-001"}]))
    assert st.item("REQ-001")["stale"]
    S.record_decision(st, checkpoint="13R", source="user", timestamp="t", answer=answer([{"type": "reconfirm", "item_id": "REQ-001"}]))
    assert not st.item("REQ-001")["stale"] and st.item("REQ-001")["approval"] == "approved"


def test_supersede_by_decision_moves_stale_item_out():
    st = state(**{"REQ-001": {"approval": "approved", "decision_ids": ["DEC-001"], "stale": True, "stale_reason": "x"},
                  "REQ-002": {}})
    st.decisions["decisions"].append({"id": "DEC-001"})
    S.record_decision(st, checkpoint="13R", source="user", timestamp="t",
                      answer=answer([{"type": "supersede", "item_id": "REQ-001", "replacement_id": "REQ-002"}]))
    it = st.item("REQ-001")
    assert it["approval"] == "superseded" and not it["stale"] and it["superseded_by"] == "REQ-002"


def test_reconfirm_requires_stale_approved_item():
    st = state(**{"REQ-001": {}})
    with pytest.raises(S.StatusError):
        S.record_decision(st, checkpoint="13R", source="user", timestamp="t", answer=answer([{"type": "reconfirm", "item_id": "REQ-001"}]))


# --------------------------------------------------------------------------- verification


def test_finding_cannot_be_approved_unless_kept():
    for v in ("pending", "dropped", "citation_failed"):
        st = state(**{"F-GAP-001-01": {"kind": "finding", "provenance": "research_evidence", "verification": v}})
        with pytest.raises(S.StatusError, match="verification"):
            S.transition(st, "F-GAP-001-01", "approved", dec="DEC-001")
    st = state(**{"F-GAP-001-01": {"kind": "finding", "provenance": "research_evidence", "verification": "kept"}})
    S.transition(st, "F-GAP-001-01", "approved", dec="DEC-001")


def test_findings_register_pending():
    assert S.new_item("F-GAP-001-01", "finding", "research_evidence", "findings/GAP-001.json")["verification"] == "pending"


# --------------------------------------------------------------------------- decisions


def test_decision_creates_requirement_and_gap_never_reusing_ids():
    st = state(**{"REQ-001": {}, "REQ-002": {}})
    dec = S.record_decision(st, checkpoint="1", source="user", timestamp="t", agent_req_ids=["REQ-003"],
                            answer=answer([{"type": "create_requirement", "statement": "Only managers award."},
                                           {"type": "create_gap", "title": "Audit", "description": "d",
                                            "resolution_path": "customer"}]))
    d = st.decisions["decisions"][-1]
    ids = [c["id"] for c in d["created_items"]]
    assert ids == ["REQ-004", "GAP-001"]
    r = st.item("REQ-004")
    assert r["provenance"] == "user_decision" and r["approval"] == "approved" and r["decision_ids"] == [dec]


def test_research_gap_needs_questions():
    st = state()
    with pytest.raises(S.StatusError, match="research_questions"):
        S.record_decision(st, checkpoint="2", source="user", timestamp="t",
                          answer=answer([{"type": "create_gap", "title": "t", "description": "d", "resolution_path": "research"}]))


def test_supersedes_links_both_ways():
    st = state(**{"REQ-001": {}})
    d1 = S.record_decision(st, checkpoint="1", source="user", timestamp="t", answer=answer([{"type": "defer", "item_id": "REQ-001"}]))
    d2 = S.record_decision(st, checkpoint="1", source="user", timestamp="t",
                           answer={**answer([{"type": "approve", "item_id": "REQ-001"}]), "supersedes": d1})
    decs = {d["id"]: d for d in st.decisions["decisions"]}
    assert decs[d1]["superseded_by"] == d2 and decs[d2]["supersedes"] == d1
    with pytest.raises(S.StatusError, match="already superseded"):
        S.record_decision(st, checkpoint="1", source="user", timestamp="t", answer={**answer([]), "supersedes": d1})


def test_rejected_item_needs_reopen_before_approval():
    st = state(**{"GAP-001": {"kind": "gap", "provenance": "inference"}})
    S.record_decision(st, checkpoint="2", source="user", timestamp="t", answer=answer([{"type": "reject", "item_id": "GAP-001"}]))
    with pytest.raises(S.StatusError):
        S.record_decision(st, checkpoint="2", source="user", timestamp="t", answer=answer([{"type": "approve", "item_id": "GAP-001"}]))
    S.record_decision(st, checkpoint="2", source="user", timestamp="t", answer=answer([{"type": "reopen", "item_id": "GAP-001"}]))
    S.record_decision(st, checkpoint="2", source="user", timestamp="t", answer=answer([{"type": "approve", "item_id": "GAP-001"}]))
    assert st.item("GAP-001")["approval"] == "approved"


def test_proposed_changes_are_idempotent():
    st = state(**{"REQ-001": {}})
    for _ in range(2):
        S.apply_proposed(st, {"type": "add_issue", "item_id": "REQ-001", "issue": "unknown", "reason": "r"})
        S.apply_proposed(st, {"type": "request_user_input", "item_id": "REQ-001", "reason": "r"})
    it = st.item("REQ-001")
    assert it["issues"] == ["unknown"] and it["approval"] == "awaiting_user_input"


# --------------------------------------------------------------------------- labels and placement


@pytest.mark.parametrize("kw,label,placement", [
    ({"approval": "rejected", "decision_ids": ["DEC-006"]}, "Rejected: DEC-006", "out_of_scope_rejected"),
    ({"approval": "deferred", "decision_ids": ["DEC-007"]}, "Deferred: DEC-007", "deferred"),
    ({"approval": "superseded", "decision_ids": ["DEC-002"], "superseded_by": "REQ-009"}, "Superseded by REQ-009: DEC-002", "decisions_log"),
    ({"approval": "approved", "decision_ids": ["DEC-003"], "stale": True, "stale_reason": "x", "issues": ["conflicting"]},
     "Stale: re-confirm (DEC-003)", "main_body"),
    ({"issues": ["conflicting", "unknown"]}, "Conflicting", "main_body"),
    ({"issues": ["unknown"], "approval": "approved", "decision_ids": ["DEC-001"]}, "Unknown", "main_body"),
    ({"provenance": "user_decision", "dec": "DEC-004"}, "Decided: DEC-004", "main_body"),
    ({"approval": "approved", "decision_ids": ["DEC-001", "DEC-002"]}, "Approved: DEC-002", "main_body"),
    ({"kind": "recommendation", "provenance": "inference"}, "Recommended (awaiting approval)", "main_body"),
    ({}, "Explicit", "main_body"),
    ({"kind": "finding", "provenance": "research_evidence", "verification": "kept"}, "Research-supported", "main_body"),
    ({"kind": "gap", "provenance": "inference"}, "Inferred", "main_body"),
    ({"kind": "assumption", "provenance": "assumption"}, "Assumption", "main_body"),
    ({"kind": "gap", "provenance": "mockup_observation"}, "Observed", "main_body"),
    ({"kind": "finding", "provenance": "research_evidence", "verification": "dropped"}, "Dropped", "sources_limitations"),
    ({"kind": "finding", "provenance": "research_evidence", "verification": "citation_failed"}, "Citation failed", "sources_limitations"),
    ({"kind": "finding", "provenance": "research_evidence", "verification": "pending"}, "Pending verification", "nowhere"),
    ({"kind": "recommendation", "provenance": "research_evidence", "verification": "kept", "approval": "approved",
      "decision_ids": ["DEC-008"]}, "Approved: DEC-008", "main_body"),
])
def test_label_and_placement(kw, label, placement):
    iid = "F-GAP-001-01" if kw.get("kind") in ("finding", "recommendation") and kw.get("provenance") == "research_evidence" else "REQ-001"
    st = state(**{iid: kw})
    out = S.label(st.item(iid))
    assert (out["label"], out["placement"]) == (label, placement)


def test_research_supported_never_means_approved():
    st = state(**{"F-GAP-001-01": {"kind": "finding", "provenance": "research_evidence", "verification": "kept"}})
    assert "Approved" not in S.label(st.item("F-GAP-001-01"))["label"]


def test_gap_routing_overrides_and_research_allowed():
    st = state(**{"GAP-001": {"kind": "gap", "provenance": "inference"}, "GAP-002": {"kind": "gap", "provenance": "inference"}})
    gaps = {"gaps": [{"id": "GAP-001", "resolution_path": "customer", "priority": "optional", "research_questions": []},
                     {"id": "GAP-002", "resolution_path": "research", "priority": "important", "research_questions": ["q"]}]}
    S.record_decision(st, checkpoint="2", source="user", timestamp="t", answer=answer([
        {"type": "approve", "item_id": "GAP-001"},
        {"type": "set_resolution_path", "item_id": "GAP-001", "resolution_path": "both"},
        {"type": "set_research_questions", "item_id": "GAP-001", "research_questions": ["Which standard applies?"]},
        {"type": "set_priority", "item_id": "GAP-001", "priority": "critical"},
        {"type": "reject", "item_id": "GAP-002"}]))
    r = S.gap_routing(st.registry, st.decisions, gaps)
    assert r["GAP-001"] == {"approval": "approved", "resolution_path": "both", "priority": "critical",
                            "research_questions": ["Which standard applies?"], "research_allowed": True}
    assert r["GAP-002"]["research_allowed"] is False
