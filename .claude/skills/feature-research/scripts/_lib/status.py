"""Status model (BUILD_SPEC §6): registry entries, transitions, decisions, labels. Pure logic.

Nothing here touches the filesystem; status_rules.py loads, calls these functions on copies,
and writes the results only if every change is valid (all or nothing).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

APPROVALS = ("not_reviewed", "awaiting_user_input", "approved", "rejected", "deferred", "superseded")

# (from, to) -> what the change requires: "reason", "dec", or "dec_or_stale".
TRANSITIONS: dict[tuple[str, str], str] = {
    ("not_reviewed", "awaiting_user_input"): "reason",
    ("not_reviewed", "approved"): "dec",
    ("not_reviewed", "rejected"): "dec",
    ("not_reviewed", "deferred"): "dec",
    ("not_reviewed", "superseded"): "dec_or_stale",
    ("awaiting_user_input", "approved"): "dec",
    ("awaiting_user_input", "rejected"): "dec",
    ("awaiting_user_input", "deferred"): "dec",
    ("awaiting_user_input", "superseded"): "dec_or_stale",
    ("deferred", "awaiting_user_input"): "reason",
    ("deferred", "approved"): "dec",
    ("deferred", "rejected"): "dec",
    ("deferred", "superseded"): "dec_or_stale",
    ("approved", "superseded"): "dec",
    ("rejected", "awaiting_user_input"): "dec",
}

ID_PREFIX = {"REQ": r"^REQ-(\d+)$", "GAP": r"^GAP-(\d+)$", "DEC": r"^DEC-(\d+)$"}


class StatusError(ValueError):
    pass


@dataclass
class Change:
    item_id: str
    field: str
    old: object
    new: object
    reason: str | None = None
    decision_id: str | None = None
    stale_reason: str | None = None


@dataclass
class State:
    registry: dict
    decisions: dict
    changes: list = field(default_factory=list)

    def item(self, item_id: str) -> dict:
        try:
            return self.registry["items"][item_id]
        except KeyError:
            raise StatusError(f"{item_id} is not registered") from None


def new_item(item_id: str, kind: str, provenance: str, source: str, dec: str | None = None) -> dict:
    item = {"id": item_id, "kind": kind, "provenance": provenance, "source_artifact": source,
            "approval": "approved" if provenance == "user_decision" else "not_reviewed",
            "issues": [], "decision_ids": [dec] if dec else [], "stale": False, "stale_reason": None,
            "superseded_by": None}
    if provenance == "user_decision" and not dec:
        raise StatusError(f"{item_id}: user_decision items need the DEC that created them")
    if kind in ("finding", "recommendation") and item_id.startswith("F-"):
        item["verification"] = "pending"
    return item


def register_item(st: State, item: dict) -> None:
    items = st.registry["items"]
    if item["id"] in items:
        existing = items[item["id"]]
        if existing["source_artifact"] != item["source_artifact"]:
            raise StatusError(f"duplicate id {item['id']}: already registered from {existing['source_artifact']}")
        return  # re-registration of a revised artifact keeps the status
    items[item["id"]] = item
    st.changes.append(Change(item["id"], "registered", None, {k: item[k] for k in ("kind", "provenance", "approval")},
                             reason=f"registered from {item['source_artifact']}", decision_id=(item["decision_ids"] or [None])[0]))


def transition(st: State, item_id: str, to: str, *, dec: str | None = None, reason: str | None = None,
               stale_reason: str | None = None) -> None:
    item = st.item(item_id)
    frm = item["approval"]
    if frm == to:
        return
    need = TRANSITIONS.get((frm, to))
    if need is None:
        raise StatusError(f"{item_id}: {frm} -> {to} is not a valid transition")
    if need == "dec" and not dec:
        raise StatusError(f"{item_id}: {frm} -> {to} requires a decision (DEC)")
    if need == "reason" and not (reason or dec):
        raise StatusError(f"{item_id}: {frm} -> {to} requires a reason")
    if need == "dec_or_stale" and not (dec or stale_reason):
        raise StatusError(f"{item_id}: {frm} -> {to} requires a decision or a stale reason")
    if to == "approved" and "verification" in item and item["verification"] != "kept":
        raise StatusError(f"{item_id}: a finding can be approved only when its verification is kept "
                          f"(is {item['verification']})")
    item["approval"] = to
    st.changes.append(Change(item_id, "approval", frm, to, reason, dec, stale_reason))
    if dec:
        _link_dec(st, item, dec)


def _link_dec(st: State, item: dict, dec: str) -> None:
    if dec not in item["decision_ids"]:
        old = list(item["decision_ids"])
        item["decision_ids"].append(dec)
        st.changes.append(Change(item["id"], "decision_ids", old, list(item["decision_ids"]), decision_id=dec))


def add_issue(st: State, item_id: str, issue: str, reason: str) -> None:
    item = st.item(item_id)
    if issue not in item["issues"]:
        old = list(item["issues"])
        item["issues"].append(issue)
        st.changes.append(Change(item_id, "issues", old, list(item["issues"]), reason))


def clear_issue(st: State, item_id: str, issue: str, dec: str) -> None:
    item = st.item(item_id)
    if issue not in item["issues"]:
        raise StatusError(f"{item_id} has no {issue!r} issue to clear")
    old = list(item["issues"])
    item["issues"].remove(issue)
    st.changes.append(Change(item_id, "issues", old, list(item["issues"]), "cleared by decision", dec))
    _link_dec(st, item, dec)


def apply_proposed(st: State, change: dict) -> None:
    """Apply one agent-proposed change. Idempotent, so re-registering a revised artifact is safe."""
    if change["type"] == "add_issue":
        add_issue(st, change["item_id"], change["issue"], change["reason"])
    elif change["type"] == "request_user_input":
        item = st.item(change["item_id"])
        if item["approval"] in ("not_reviewed", "deferred"):
            transition(st, change["item_id"], "awaiting_user_input", reason=change["reason"])


def next_id(st: State, prefix: str) -> str:
    pat = re.compile(ID_PREFIX[prefix])
    pool = list(st.registry["items"]) if prefix != "DEC" else [d["id"] for d in st.decisions["decisions"]]
    nums = [int(m.group(1)) for i in pool if (m := pat.match(i))]
    return f"{prefix}-{(max(nums) + 1 if nums else 1):03d}"


def max_existing(ids, prefix: str) -> int:
    pat = re.compile(ID_PREFIX[prefix])
    return max([int(m.group(1)) for i in ids if (m := pat.match(i))] or [0])


# --------------------------------------------------------------------------- decisions


def record_decision(st: State, *, checkpoint: str, source: str, answer: dict, timestamp: str,
                    agent_req_ids=(), agent_gap_ids=()) -> str:
    """Create one DEC for one answer and apply its actions. Returns the DEC id."""
    dec_id = next_id(st, "DEC")
    created: list[dict] = []
    dec = {"id": dec_id, "checkpoint": checkpoint, "source": source, "presented": answer["presented"],
           "verbatim": answer["verbatim"], "interpretation": answer["interpretation"],
           "affected_ids": list(answer.get("affected_ids", [])), "actions": copy.deepcopy(answer.get("actions", [])),
           "created_items": created, "timestamp": timestamp, "supersedes": answer.get("supersedes"),
           "superseded_by": None}
    if answer.get("question_ids"):
        dec["question_ids"] = list(answer["question_ids"])
    if dec["supersedes"]:
        old = next((d for d in st.decisions["decisions"] if d["id"] == dec["supersedes"]), None)
        if old is None:
            raise StatusError(f"{dec_id}: supersedes unknown decision {dec['supersedes']}")
        if old["superseded_by"]:
            raise StatusError(f"{old['id']} is already superseded by {old['superseded_by']}")
        old["superseded_by"] = dec_id
        st.changes.append(Change(old["id"], "superseded_by", None, dec_id, "decision superseded", dec_id))
    st.decisions["decisions"].append(dec)
    st.changes.append(Change(dec_id, "decision", None, {"checkpoint": checkpoint, "source": source}, None, dec_id))

    for act in answer.get("actions", []):
        t = act["type"]
        iid = act.get("item_id")
        if t in ("approve", "reject", "defer", "reopen", "supersede", "reconfirm", "clear_issue",
                 "set_priority", "set_resolution_path", "set_research_questions") and not iid:
            raise StatusError(f"{dec_id}: action {t} needs item_id")
        if t == "approve":
            transition(st, iid, "approved", dec=dec_id)
        elif t == "reject":
            transition(st, iid, "rejected", dec=dec_id)
        elif t == "defer":
            transition(st, iid, "deferred", dec=dec_id)
        elif t == "reopen":
            transition(st, iid, "awaiting_user_input", dec=dec_id, reason="reopened by decision")
        elif t == "supersede":
            item = st.item(iid)
            transition(st, iid, "superseded", dec=dec_id)
            if act.get("replacement_id"):
                st.item(act["replacement_id"])
                item["superseded_by"] = act["replacement_id"]
                st.changes.append(Change(iid, "superseded_by", None, act["replacement_id"], None, dec_id))
            if item["stale"]:
                _set_stale(st, item, False, None, dec_id)
        elif t == "reconfirm":
            item = st.item(iid)
            if not item["stale"]:
                raise StatusError(f"{iid} is not stale; nothing to re-confirm")
            if item["approval"] != "approved":
                raise StatusError(f"{iid} is {item['approval']}; only approved stale items are re-confirmed")
            _set_stale(st, item, False, None, dec_id)
            _link_dec(st, item, dec_id)
        elif t == "clear_issue":
            if not act.get("issue"):
                raise StatusError(f"{dec_id}: clear_issue needs issue")
            clear_issue(st, iid, act["issue"], dec_id)
        elif t in ("set_priority", "set_resolution_path", "set_research_questions"):
            item = st.item(iid)
            if item["kind"] != "gap":
                raise StatusError(f"{dec_id}: {t} applies to gaps, not {iid}")
            need = {"set_priority": "priority", "set_resolution_path": "resolution_path",
                    "set_research_questions": "research_questions"}[t]
            if need not in act:
                raise StatusError(f"{dec_id}: {t} needs {need}")
            if t == "set_priority" and act["priority"] not in ("critical", "important", "optional"):
                raise StatusError(f"{dec_id}: gap priority must be critical, important or optional")
            _link_dec(st, item, dec_id)
        elif t == "create_requirement":
            if not act.get("statement"):
                raise StatusError(f"{dec_id}: create_requirement needs statement")
            rid = _next_fresh(st, "REQ", agent_req_ids)
            register_item(st, new_item(rid, "requirement", "user_decision", "decisions.json", dec_id))
            created.append({"id": rid, "kind": "requirement", "statement": act["statement"],
                            "req_type": act.get("req_type", "functional"), "priority": act.get("priority", "unspecified")})
        elif t == "create_gap":
            for k in ("title", "description", "resolution_path"):
                if not act.get(k):
                    raise StatusError(f"{dec_id}: create_gap needs {k}")
            rq = act.get("research_questions", [])
            if act["resolution_path"] != "customer" and not rq:
                raise StatusError(f"{dec_id}: a gap routed to research needs research_questions")
            gid = _next_fresh(st, "GAP", agent_gap_ids)
            register_item(st, new_item(gid, "gap", "user_decision", "decisions.json", dec_id))
            created.append({"id": gid, "kind": "gap", "title": act["title"], "description": act["description"],
                            "resolution_path": act["resolution_path"], "priority": act.get("priority", "important"),
                            "research_questions": rq})
        elif t == "leave_open":
            if iid:
                st.item(iid)
        else:
            raise StatusError(f"unknown action {t}")
    return dec_id


def _next_fresh(st: State, prefix: str, agent_ids) -> str:
    """Never reuse an id, including ids an agent artifact uses but that are not registered yet."""
    n = max(max_existing(st.registry["items"], prefix), max_existing(agent_ids, prefix)) + 1
    return f"{prefix}-{n:03d}"


def _set_stale(st: State, item: dict, value: bool, reason: str | None, dec: str | None) -> None:
    old = (item["stale"], item["stale_reason"])
    item["stale"], item["stale_reason"] = value, reason
    st.changes.append(Change(item["id"], "stale", old[0], value, "cleared by decision" if not value else None, dec,
                             reason if value else old[1]))


VERIFICATION_TRANSITIONS = {("pending", "citation_failed"), ("pending", "kept"), ("pending", "dropped")}


def set_verification(st: State, item_id: str, value: str, reason: str) -> None:
    """Only status_rules.py verification calls this, from citation_check.json or verified_findings.json."""
    item = st.item(item_id)
    if "verification" not in item:
        raise StatusError(f"{item_id} is not a finding")
    old = item["verification"]
    if old == value:
        return
    if (old, value) not in VERIFICATION_TRANSITIONS:
        raise StatusError(f"{item_id}: verification {old} -> {value} is not allowed")
    item["verification"] = value
    st.changes.append(Change(item_id, "verification", old, value, reason))


def apply_stale(st: State, item_id: str, stale_reason: str) -> None:
    """Change-impact analysis (§15): approved items stay approved and become stale; others are superseded."""
    item = st.item(item_id)
    if item["approval"] == "approved":
        _set_stale(st, item, True, stale_reason, None)
    elif item["approval"] in ("not_reviewed", "awaiting_user_input", "deferred"):
        _set_stale(st, item, True, stale_reason, None)
        transition(st, item_id, "superseded", stale_reason=stale_reason)


# --------------------------------------------------------------------------- labels


def latest_dec(item: dict) -> str | None:
    return item["decision_ids"][-1] if item["decision_ids"] else None


def label(item: dict) -> dict:
    """Placement first, then the first matching label (§6, Placement and display labels)."""
    dec = latest_dec(item)
    appr = item["approval"]
    ver = item.get("verification")
    if appr == "rejected":
        return {"label": f"Rejected: {dec}", "placement": "out_of_scope_rejected", "decision_id": dec}
    if appr == "deferred":
        return {"label": f"Deferred: {dec}", "placement": "deferred", "decision_id": dec}
    if appr == "superseded":
        by = f" by {item['superseded_by']}" if item.get("superseded_by") else ""
        return {"label": f"Superseded{by}" + (f": {dec}" if dec else ""), "placement": "decisions_log", "decision_id": dec}
    if ver in ("dropped", "citation_failed"):
        return {"label": "Dropped" if ver == "dropped" else "Citation failed", "placement": "sources_limitations",
                "decision_id": dec}
    if ver == "pending":
        return {"label": "Pending verification", "placement": "nowhere", "decision_id": dec}
    open_q = False
    if item["stale"]:
        text, open_q = f"Stale: re-confirm ({dec})", True
    elif "conflicting" in item["issues"]:
        text = "Conflicting"
    elif "unknown" in item["issues"]:
        text = "Unknown"
    elif item["provenance"] == "user_decision":
        text = f"Decided: {dec}"
    elif appr == "approved":
        text = f"Approved: {dec}"
    elif item["kind"] == "recommendation":
        text = "Recommended (awaiting approval)"
    else:
        text = {"customer_requirement": "Explicit", "research_evidence": "Research-supported", "inference": "Inferred",
                "assumption": "Assumption", "mockup_observation": "Observed"}[item["provenance"]]
    out = {"label": text, "placement": "main_body", "decision_id": dec}
    if open_q:
        out["open_question"] = True
    return out


def gap_routing(registry: dict, decisions: dict, gaps_doc: dict | None) -> dict:
    base = {g["id"]: g for g in (gaps_doc or {}).get("gaps", [])}
    for d in decisions["decisions"]:
        for c in d["created_items"]:
            if c["kind"] == "gap":
                base[c["id"]] = {"resolution_path": c["resolution_path"], "priority": c.get("priority", "important"),
                                 "research_questions": c.get("research_questions", [])}
    out = {}
    for gid, g in base.items():
        item = registry["items"].get(gid)
        if not item:
            continue
        eff = {"resolution_path": g["resolution_path"], "priority": g["priority"],
               "research_questions": list(g.get("research_questions", []))}
        for d in decisions["decisions"]:
            if d["id"] not in item["decision_ids"]:
                continue
            for a in d["actions"]:
                if a.get("item_id") != gid:
                    continue
                if a["type"] == "set_priority":
                    eff["priority"] = a["priority"]
                elif a["type"] == "set_resolution_path":
                    eff["resolution_path"] = a["resolution_path"]
                elif a["type"] == "set_research_questions":
                    eff["research_questions"] = list(a["research_questions"])
        out[gid] = {"approval": item["approval"], **eff,
                    "research_allowed": item["approval"] == "approved" and not item["stale"]
                    and eff["resolution_path"] in ("research", "both") and bool(eff["research_questions"])}
    return out
