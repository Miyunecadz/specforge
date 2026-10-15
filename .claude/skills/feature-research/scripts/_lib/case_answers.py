"""Deterministic matching of pre-written eval answers to generated questions (BUILD_SPEC §16).

Answers in evals/cases/<case>/input.json are matched to the run's questions by topic keywords,
affected REQ ids and description text, never by generated question ids. An answer covers
every question it matches. A question matched by no answer, or by more than one, is left
unanswered and reported, as is an answer that matches nothing. The output is a decide-ready answers document with source
"eval_case_file"; every verbatim comes from the case file.
"""

from __future__ import annotations

import json
from pathlib import Path

APPROVABLE = ("not_reviewed", "awaiting_user_input", "deferred")


def _text(*parts) -> str:
    return " ".join(str(p) for p in parts if p).lower()


def _matches(match: dict, haystack: str, ids: list[str]) -> bool:
    """Top-level conditions must all hold; with any_of, at least one alternative must hold too."""
    if not _conditions(match, haystack, ids):
        return False
    alts = match.get("any_of")
    return not alts or any(_conditions(a, haystack, ids) for a in alts)


def _conditions(match: dict, haystack: str, ids: list[str]) -> bool:
    if any(k.lower() not in haystack for k in match.get("keywords", [])):
        return False
    if any(k.lower() in haystack for k in match.get("exclude_keywords", [])):
        return False
    if any(r not in ids for r in match.get("affected_req_ids", [])):
        return False
    if any(c.lower() not in haystack for c in match.get("description_contains", [])):
        return False
    return True


class Planner:
    """Tracks the approvals and issues the planned actions will produce, so every action is valid."""

    def __init__(self, registry: dict):
        self.items = {i: {"approval": it["approval"], "issues": list(it["issues"]), "verification": it.get("verification"),
                          "stale": it["stale"]} for i, it in registry["items"].items()}

    def approve(self, i):
        it = self.items.get(i)
        if not it or it["approval"] not in APPROVABLE:
            return None
        if it["verification"] not in (None, "kept"):
            return None
        it["approval"] = "approved"
        return {"type": "approve", "item_id": i}

    def set_approval(self, i, kind):
        it = self.items.get(i)
        if not it or it["approval"] not in APPROVABLE:
            return None
        if kind == "reject" and it["approval"] == "rejected":
            return None
        it["approval"] = {"reject": "rejected", "defer": "deferred"}[kind]
        return {"type": kind, "item_id": i}

    def reconfirm(self, i):
        it = self.items.get(i)
        if not it or not it["stale"] or it["approval"] != "approved":
            return None
        it["stale"] = False
        return {"type": "reconfirm", "item_id": i}

    def supersede(self, i):
        it = self.items.get(i)
        if not it or it["approval"] in ("rejected", "superseded"):
            return None
        it["approval"], it["stale"] = "superseded", False
        return {"type": "supersede", "item_id": i}

    def clear(self, i, issue="unknown"):
        it = self.items.get(i)
        if not it or issue not in it["issues"]:
            return None
        it["issues"].remove(issue)
        return {"type": "clear_issue", "item_id": i, "issue": issue}


def _translate(actions: list[dict], affected: list[str], plan: Planner) -> list[dict]:
    out = []
    tracked = [a for a in affected if a.startswith(("REQ-", "GAP-", "F-GAP-", "FEA-", "ASM-"))]
    for act in actions:
        t = act["type"]
        if t == "approve_affected":
            out += [x for x in (plan.approve(i) for i in tracked) if x]
        elif t in ("reject_affected", "defer_affected"):
            out += [x for x in (plan.set_approval(i, t.split("_")[0]) for i in tracked) if x]
        elif t == "clear_unknown_on_affected":
            out += [x for x in (plan.clear(i) for i in tracked) if x]
        elif t == "create_requirement":
            out.append({"type": "create_requirement", "statement": act["statement"],
                        "req_type": act.get("req_type", "functional"), "priority": act.get("priority", "unspecified")})
        elif t == "reconfirm":
            out += [x for x in (plan.reconfirm(i) for i in tracked) if x]
        elif t == "supersede_with_new_requirement":
            out.append({"type": "create_requirement", "statement": act["statement"],
                        "req_type": act.get("req_type", "functional"), "priority": act.get("priority", "unspecified")})
            out += [x for x in (plan.supersede(i) for i in tracked) if x]
        elif t == "leave_open":
            out.append({"type": "leave_open"})
    return out


def plan_checkpoint(cp: str, case: dict, run_dir: Path) -> tuple[list[dict], list[dict]]:
    """Return (answers, unmatched). Answers follow checkpoint_answers.schema.json#/$defs/answer."""
    load = lambda rel: json.loads((run_dir / rel).read_text(encoding="utf-8")) if (run_dir / rel).exists() else {}
    registry = load("status_registry.json") or {"items": {}}
    plan = Planner(registry)
    spec = case.get("checkpoints", {}).get(cp)
    answers, unmatched = [], []
    if not spec:
        return answers, [{"reason": f"the case file has no answers for checkpoint {cp}"}]

    def answer_questions(questions: list[dict], qtext, qids):
        case_answers = spec.get("answers", [])
        by_q = {q["id"]: [i for i, a in enumerate(case_answers) if _matches(a["match"], qtext(q), qids(q))] for q in questions}
        used = {i for hits in by_q.values() for i in hits}
        for i, a in enumerate(case_answers):
            if i not in used:
                unmatched.append({"verbatim": a["verbatim"], "match": a["match"], "reason": "no question matched"})
        for q in questions:
            hits = by_q[q["id"]]
            if len(hits) != 1:
                unmatched.append({"question_id": q["id"], "reason": "no pre-written answer matched this question; left open" if not hits
                                  else f"{len(hits)} pre-written answers matched this question; left open"})
                continue
            a = case_answers[hits[0]]
            affected = qids(q)
            acts = _translate(a["actions"], affected, plan)
            answers.append({"verbatim": a["verbatim"], "interpretation": a.get("interpretation") or
                            f"Pre-written eval answer matched to {q['id']} by keywords.",
                            "presented": q.get("question") or q.get("id"), "question_ids": [q["id"]] if q["id"].startswith(("CQ-", "Q-")) else [],
                            "affected_ids": [x for x in affected if not x.startswith("SRC-")], "actions": acts})

    if cp == "1":
        cqs = load("requirements.json").get("clarifying_questions", [])
        # Question text and topic only: why_it_matters mentions neighbouring topics and causes false matches.
        answer_questions(cqs, lambda q: _text(q["question"], q.get("topic"), " ".join(q["related_ids"])),
                         lambda q: list(q["related_ids"]))
        rem = spec.get("remaining_requirements")
        if rem and rem["decision"] == "approve":
            acts = [x for x in (plan.approve(i) for i in sorted(plan.items) if i.startswith("REQ-")) if x]
            if acts:
                answers.append({"verbatim": rem["verbatim"], "interpretation": "Approve every remaining requirement as written.",
                                "presented": "Remaining requirements", "question_ids": [], "affected_ids": [a["item_id"] for a in acts],
                                "actions": acts})
    elif cp == "2":
        gaps = [g for g in load("gaps.json").get("gaps", []) if plan.items.get(g["id"], {}).get("approval") in APPROVABLE]
        cap = spec.get("max_research_gaps")
        researched = 0
        decided: dict[str, tuple[str, dict]] = {}
        for g in gaps:
            hay = _text(g["title"], g["description"], g["category"], " ".join(g["related_req_ids"]))
            rules = [r for r in spec["gap_rules"] if _matches(r["match"], hay, g["related_req_ids"])]
            if len(rules) > 1:
                unmatched.append({"gap_id": g["id"], "reason": f"{len(rules)} gap rules matched; using the unmatched default"})
                rules = []
            decided[g["id"]] = (rules[0]["decision"], rules[0]) if rules else (spec["unmatched_gaps"]["decision"], None)
        groups: dict[str, list] = {}
        for g in gaps:
            decision, rule = decided[g["id"]]
            path = (rule or {}).get("resolution_path") or g["resolution_path"]
            if decision == "approve" and path in ("research", "both") and cap is not None:
                if researched >= cap:
                    decision = "defer"
                    unmatched.append({"gap_id": g["id"], "reason": f"max_research_gaps={cap} reached; deferred"})
                else:
                    researched += 1
            verbatim = rule["verbatim"] if rule and decision == rule["decision"] else spec["unmatched_gaps"]["verbatim"]
            act = plan.approve(g["id"]) if decision == "approve" else plan.set_approval(g["id"], decision)
            acts = [act] if act else []
            if rule and rule.get("resolution_path") and decision == "approve":
                acts.append({"type": "set_resolution_path", "item_id": g["id"], "resolution_path": rule["resolution_path"]})
            groups.setdefault(verbatim, []).extend(acts)
        for verbatim, acts in groups.items():
            if acts:
                answers.append({"verbatim": verbatim, "interpretation": "Gap decisions from the eval case file.",
                                "presented": "Gap table", "question_ids": [], "affected_ids": sorted({a["item_id"] for a in acts}),
                                "actions": acts})
    elif cp == "3":
        qs = load("questions.json").get("questions", [])
        answer_questions(qs, lambda q: _text(q["question"], " ".join(q["topic_keywords"]), " ".join(q["affected_ids"])),
                         lambda q: list(q["affected_ids"]))
    elif cp == "13R":
        texts = {r["id"]: r["statement"] + " " + r["source_quote"] for r in load("requirements.json").get("requirements", [])}
        texts.update({g["id"]: g["title"] + " " + g["description"] for g in load("gaps.json").get("gaps", [])})
        texts.update({f["id"]: f["title"] + " " + f.get("description", "") for f in load("feasibility.json").get("items", [])})
        pending = [{"id": i, "text": texts.get(i, ""), "reason": it.get("stale_reason") or ""}
                   for i, it in sorted(registry["items"].items()) if it["stale"] and it["approval"] == "approved"]
        if spec.get("answers"):
            answer_questions(pending, lambda q: _text(q["id"], q["text"], q["reason"]), lambda q: [q["id"]])
            unmatched[:] = [u for u in unmatched if "question_id" not in u]  # the default covers the rest
        stale = sorted(i for i, it in plan.items.items() if it["stale"] and it["approval"] == "approved")
        if stale and spec.get("verbatim"):
            acts = [{"type": "reconfirm", "item_id": i} for i in stale] if spec["default"] == "reconfirm" else \
                [{"type": "leave_open", "item_id": i} for i in stale]
            answers.append({"verbatim": spec["verbatim"], "interpretation": f"Default for stale items: {spec['default']}.",
                            "presented": "Stale approved items", "question_ids": [], "affected_ids": stale, "actions": acts})
    return answers, unmatched
