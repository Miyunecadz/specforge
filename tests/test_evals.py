"""Phase 6: answer matching, decide --from-case, change impact, metrics, run_evals helpers and the case set (§15, §16)."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

import provenance
import run_evals
import run_state
import status_rules
from _lib import case_answers, metrics, schema
from conftest import REPO, SESSION, add_subagent_event, attest_for, env_for, run_cli, script_argv
from test_checkpoints import REQ_TEXT, b64, answers, ans, open_and_continue, requirements_doc, to_stage5
from test_run_state import _capture_manifest, _inventory

FX = "evals/fixtures/case-a"
CASE_REL = "evals/cases/case-a/input.json"


# --------------------------------------------------------------------------- answer matching (pure)


def reg_item(approval="not_reviewed", issues=(), stale=False, verification=None, reason=None):
    return {"approval": approval, "issues": list(issues), "stale": stale, "verification": verification, "stale_reason": reason}


def write_run(tmp_path, registry, **docs):
    rd = tmp_path / "run"
    rd.mkdir()
    (rd / "status_registry.json").write_text(json.dumps({"items": registry}))
    for name, doc in docs.items():
        (rd / f"{name}.json").write_text(json.dumps(doc))
    return rd


def cq(i, question, related, why="w"):
    return {"id": f"CQ-00{i}", "question": question, "why_it_matters": why, "blocking": True, "related_ids": related,
            "consequence_if_unanswered": "c"}


def m_answer(keywords, verbatim, actions, **match):
    return {"match": {"keywords": keywords, **match}, "verbatim": verbatim, "actions": [{"type": a} if isinstance(a, str) else a for a in actions]}


def test_cp1_matches_by_keywords_and_approves_remaining(tmp_path):
    rd = write_run(tmp_path, {"REQ-001": reg_item(issues=["unknown"]), "REQ-002": reg_item(), "REQ-003": reg_item(approval="rejected")},
                   requirements={"clarifying_questions": [cq(1, "Who counts as a package manager?", ["REQ-001"]),
                                                          cq(2, "Which export format?", ["REQ-002"])]})
    case = {"checkpoints": {"1": {"answers": [m_answer(["package manager"], "Only Procurement.", ["approve_affected", "clear_unknown_on_affected"]),
                                              m_answer(["colour"], "Blue.", ["approve_affected"])],
                                  "remaining_requirements": {"decision": "approve", "verbatim": "Approve the rest."}}}}
    got, unmatched = case_answers.plan_checkpoint("1", case, rd)
    assert got[0]["question_ids"] == ["CQ-001"]
    assert got[0]["actions"] == [{"type": "approve", "item_id": "REQ-001"}, {"type": "clear_issue", "item_id": "REQ-001", "issue": "unknown"}]
    assert got[1]["actions"] == [{"type": "approve", "item_id": "REQ-002"}]  # REQ-001 already approved, REQ-003 rejected
    assert {"verbatim": "Blue."}.items() <= unmatched[0].items() and unmatched[0]["reason"] == "no question matched"
    assert any(u.get("question_id") == "CQ-002" for u in unmatched)


def test_answer_covers_every_question_it_matches(tmp_path):
    rd = write_run(tmp_path, {"REQ-001": reg_item(), "REQ-002": reg_item()},
                   requirements={"clarifying_questions": [cq(1, "Who can award a package?", ["REQ-001"]),
                                                          cq(2, "Who can export a package?", ["REQ-002"])]})
    case = {"checkpoints": {"1": {"answers": [m_answer(["package"], "Managers.", ["approve_affected"])]}}}
    got, unmatched = case_answers.plan_checkpoint("1", case, rd)
    assert [g["question_ids"] for g in got] == [["CQ-001"], ["CQ-002"]] and unmatched == []
    case["checkpoints"]["1"]["answers"][0]["match"]["affected_req_ids"] = ["REQ-002"]
    got, _ = case_answers.plan_checkpoint("1", case, rd)
    assert [g["question_ids"] for g in got] == [["CQ-002"]]


def test_question_matched_by_two_answers_is_left_open(tmp_path):
    rd = write_run(tmp_path, {"REQ-001": reg_item(), "REQ-002": reg_item()},
                   requirements={"clarifying_questions": [cq(1, "Who can award a package?", ["REQ-001"]),
                                                          cq(2, "Which export format?", ["REQ-002"])]})
    case = {"checkpoints": {"1": {"answers": [m_answer(["award"], "Managers.", ["approve_affected"]),
                                              m_answer(["package"], "Anyone.", ["approve_affected"])]}}}
    got, unmatched = case_answers.plan_checkpoint("1", case, rd)
    assert got == [] and unmatched == [
        {"question_id": "CQ-001", "reason": "2 pre-written answers matched this question; left open"},
        {"question_id": "CQ-002", "reason": "no pre-written answer matched this question; left open"}]


def test_any_of_alternatives(tmp_path):
    rd = write_run(tmp_path, {"REQ-001": reg_item()},
                   requirements={"clarifying_questions": [cq(1, "Can the approver be the same person who registered it?", ["REQ-001"])]})
    a = {"match": {"any_of": [{"keywords": ["self-approv"]}, {"keywords": ["approv", "regist"]}]}, "verbatim": "No.",
         "actions": [{"type": "approve_affected"}]}
    got, _ = case_answers.plan_checkpoint("1", {"checkpoints": {"1": {"answers": [a]}}}, rd)
    assert got[0]["question_ids"] == ["CQ-001"]
    a["match"]["keywords"] = ["export"]  # top-level conditions still apply
    got, _ = case_answers.plan_checkpoint("1", {"checkpoints": {"1": {"answers": [a]}}}, rd)
    assert got == []


def gap(i, title, path="research", reqs=("REQ-001",)):
    return {"id": f"GAP-00{i}", "title": title, "description": "d", "category": "states", "related_req_ids": list(reqs),
            "resolution_path": path}


def test_cp2_rules_cap_and_default(tmp_path):
    rd = write_run(tmp_path, {f"GAP-00{i}": reg_item() for i in range(1, 5)},
                   gaps={"gaps": [gap(1, "Focus handling"), gap(2, "Audit trail"), gap(3, "Duplicate awards"), gap(4, "Colour", "customer")]})
    case = {"checkpoints": {"2": {"gap_rules": [{"match": {"keywords": ["colour"]}, "decision": "reject", "verbatim": "No colour work."}],
                                  "max_research_gaps": 2, "unmatched_gaps": {"decision": "approve", "verbatim": "Approve the others."}}}}
    got, unmatched = case_answers.plan_checkpoint("2", case, rd)
    acts = {a["item_id"]: a["type"] for g in got for a in g["actions"]}
    assert acts == {"GAP-001": "approve", "GAP-002": "approve", "GAP-003": "defer", "GAP-004": "reject"}
    assert any("max_research_gaps=2" in u["reason"] for u in unmatched)
    defer = next(g for g in got if any(a["item_id"] == "GAP-003" for a in g["actions"]))
    assert defer["verbatim"] == "Approve the others."  # verbatim always comes from the case file


def test_13r_matched_answer_supersedes_and_default_covers_rest(tmp_path):
    rd = write_run(tmp_path, {"REQ-001": reg_item("approved", stale=True, reason="change 1: REQ-001 text gone"),
                              "GAP-001": reg_item("approved", stale=True, reason="change 1: depends on changed REQ-001")},
                   requirements={"requirements": [{"id": "REQ-001", "statement": "Managers award packages.", "source_quote": "Managers award."}]},
                   gaps={"gaps": [gap(1, "Award audit")]})
    case = {"checkpoints": {"13R": {"default": "reconfirm", "verbatim": "Keep the rest.",
                                    "answers": [m_answer(["managers award"], "Replace it: directors award.",
                                                         [{"type": "supersede_with_new_requirement", "statement": "Directors award packages."}])]}}}
    got, unmatched = case_answers.plan_checkpoint("13R", case, rd)
    assert got[0]["actions"] == [{"type": "create_requirement", "statement": "Directors award packages.", "req_type": "functional",
                                  "priority": "unspecified"}, {"type": "supersede", "item_id": "REQ-001"}]
    assert got[1]["affected_ids"] == ["GAP-001"] and got[1]["actions"] == [{"type": "reconfirm", "item_id": "GAP-001"}]
    assert unmatched == []


def test_missing_checkpoint_answers_reported(tmp_path):
    rd = write_run(tmp_path, {})
    assert case_answers.plan_checkpoint("3", {"checkpoints": {}}, rd) == ([], [{"reason": "the case file has no answers for checkpoint 3"}])


# --------------------------------------------------------------------------- decide --from-case (fixture mode)


def write_case(repo, cp1=None, **extra):
    d = repo / "evals/cases/case-a"
    (d / "requirements.md").write_text(REQ_TEXT)
    case = {"schema_version": 1, "case_id": "case-01a", "description": "test", "fixture_dir": FX, "mockup": "index.html",
            "requirements_file": "evals/cases/case-a/requirements.md",
            "checkpoints": {"1": cp1 or {"answers": [m_answer(["package manager"], "Only Procurement managers.",
                                                              ["approve_affected", "clear_unknown_on_affected"]),
                                                     m_answer(["colour"], "Blue.", ["approve_affected"])],
                                         "remaining_requirements": {"decision": "approve", "verbatim": "Approve the rest as written."}}},
            **extra}
    schema.check("eval_input", case)
    (d / "input.json").write_text(json.dumps(case))
    (repo / FX / "index.html").write_text("<h1>x</h1>")


def frs(repo, *args):
    return run_cli(run_state.main, script_argv(repo, "run_state", *args), repo, env_for(fixture=FX))


def fsr(repo, *args):
    return run_cli(status_rules.main, script_argv(repo, "status_rules", *args), repo, env_for(fixture=FX))


def fixture_to_stage5(repo):
    write_case(repo)
    argv = script_argv(repo, "run_state", "start", "--mockup-url", "index.html", "--requirements-file",
                       "evals/cases/case-a/requirements.md", "--non-interactive", CASE_REL)
    attest_for(repo, argv, mode="fixture")
    rc, out = run_cli(run_state.main, argv, repo, env_for(fixture=FX))
    assert rc == 0, out
    run_id = out["run_id"]
    rd = repo / "evals/runs" / run_id
    assert frs(repo, "stage", "1", "--run", run_id, "--complete")[0] == 0
    assert frs(repo, "stage", "2", "--run", run_id, "--start")[0] == 0
    cap = rd / "capture"
    (cap / "screenshots").mkdir(parents=True)
    (cap / "pages").mkdir()
    (cap / "screenshots/page-001.png").write_bytes(b"png")
    (cap / "pages/page-001.txt").write_text("Award Package")
    (cap / "manifest.json").write_text(json.dumps({**_capture_manifest(run_id), "mode": "fixture", "fixture_dir": FX}))
    rc, out = frs(repo, "stage", "2", "--run", run_id, "--complete")
    assert rc == 0, out
    assert frs(repo, "stage", "3", "--run", run_id, "--start")[0] == 0
    (rd / "inventory.json").write_text(json.dumps(_inventory(run_id)))
    add_subagent_event(repo, run_id, "mockup-extractor", mode="fixture")
    assert frs(repo, "stage", "3", "--run", run_id, "--complete")[0] == 0
    assert frs(repo, "stage", "4", "--run", run_id, "--start")[0] == 0
    (rd / "requirements.json").write_text(json.dumps(requirements_doc(run_id)))
    add_subagent_event(repo, run_id, "requirements-parser", mode="fixture")
    assert fsr(repo, "register", "requirements.json", "--run", run_id)[0] == 0
    assert frs(repo, "stage", "4", "--run", run_id, "--complete")[0] == 0
    assert frs(repo, "stage", "5", "--run", run_id, "--start")[0] == 0
    return run_id, rd


def f_open_continue(repo, run_id, cp):
    assert frs(repo, "await-user", cp, "--run", run_id)[0] == 0
    cont = script_argv(repo, "run_state", "continue", "--run", run_id)
    attest_for(repo, cont, mode="fixture")
    assert run_cli(run_state.main, cont, repo, env_for(fixture=FX))[0] == 0


def test_decide_from_case_records_eval_decisions_and_unmatched(repo):
    run_id, rd = fixture_to_stage5(repo)
    rc, out = fsr(repo, "decide", "--run", run_id, "--checkpoint", "1", "--from-case")
    assert rc == 3 and "await-user" in out["refused"]  # checkpoint not opened yet
    f_open_continue(repo, run_id, "1")
    rc, out = fsr(repo, "decide", "--run", run_id, "--checkpoint", "1", "--from-case")
    assert rc == 0, out
    decs = json.loads((rd / "decisions.json").read_text())["decisions"]
    assert [d["source"] for d in decs] == ["eval_case_file", "eval_case_file"]
    assert decs[0]["verbatim"] == "Only Procurement managers."
    reg = json.loads((rd / "status_registry.json").read_text())["items"]
    assert reg["REQ-001"]["approval"] == "approved" and reg["REQ-001"]["issues"] == []
    assert reg["REQ-002"]["approval"] == reg["REQ-003"]["approval"] == "approved"
    cp = json.loads((rd / "checkpoints/checkpoint-1-answers.json").read_text())
    reasons = [u.get("reason") for u in cp["rounds"][0]["unmatched"]]
    assert "no question matched" in reasons and any(u.get("question_id") == "CQ-002" for u in cp["rounds"][0]["unmatched"])
    assert frs(repo, "verify", "--run", run_id)[0] == 0


def test_decide_from_case_refuses_changed_case_file_and_normal_mode(repo):
    run_id, rd = fixture_to_stage5(repo)
    f_open_continue(repo, run_id, "1")
    p = repo / CASE_REL
    p.write_text(p.read_text().replace("Blue.", "Green."))
    rc, out = fsr(repo, "decide", "--run", run_id, "--checkpoint", "1", "--from-case")
    assert rc == 3 and "changed after the run started" in out["refused"]


def test_decide_from_case_refused_without_non_interactive(repo):
    run_id = to_stage5(repo)
    open_and_continue(repo, run_id, "1")
    rc, out = run_cli(status_rules.main, script_argv(repo, "status_rules", "decide", "--run", run_id, "--checkpoint", "1",
                                                     "--from-case"), repo, env_for())
    assert rc == 3 and "fixture mode" in out["refused"]


def test_provenance_from_case_rule(tmp_path):
    rd = tmp_path / "run"
    (rd / "input").mkdir(parents=True)
    argv = ["status_rules.py", "decide", "--run", "R1", "--checkpoint", "1", "--from-case"]
    split = lambda s: s.split()
    (rd / "input/request.json").write_text(json.dumps({"non_interactive_case": {"path": CASE_REL, "sha256": "0" * 64}}))
    provenance.check(argv, run_id="R1", transcript_path=None, run_dir=rd, repo=tmp_path, fixture_env=True, split=split)
    with pytest.raises(provenance.ProvenanceError, match="only in eval fixture mode"):
        provenance.check(argv, run_id="R1", transcript_path=None, run_dir=rd, repo=tmp_path, fixture_env=False, split=split)
    with pytest.raises(provenance.ProvenanceError, match="takes only"):
        provenance.check(argv + ["--answers-b64", "e30="], run_id="R1", transcript_path=None, run_dir=rd, repo=tmp_path,
                         fixture_env=True, split=split)
    (rd / "input/request.json").write_text(json.dumps({"non_interactive_case": None}))
    with pytest.raises(provenance.ProvenanceError):
        provenance.check(argv, run_id="R1", transcript_path=None, run_dir=rd, repo=tmp_path, fixture_env=True, split=split)


# --------------------------------------------------------------------------- change impact


def rs(repo, *args):
    return run_cli(run_state.main, script_argv(repo, "run_state", *args), repo, env_for())


def sr(repo, *args):
    return run_cli(status_rules.main, script_argv(repo, "status_rules", *args), repo, env_for())


def test_change_inputs_and_apply_mark_approved_stale_and_supersede_others(repo, tmp_path):
    run_id = to_stage5(repo)
    rd = repo / "runs" / run_id
    open_and_continue(repo, run_id, "1")
    a = answers("1", [ans("Approve REQ-001.", [{"type": "approve", "item_id": "REQ-001"}], question_ids=["CQ-001"], affected=["REQ-001"])])
    assert sr(repo, "decide", "--run", run_id, "--checkpoint", "1", "--answers-b64", b64(a))[0] == 0
    new = tmp_path / "v2.md"
    new.write_text("Package managers must be able to award a supplier package to one supplier only.\n"
                   "Awarded packages should be read-only.\nFinance users can export awards as CSV.\n")
    rc, out = rs(repo, "change-inputs", "--run", run_id, "--requirements-file", str(new), "--reason", "customer email")
    assert rc == 3 and "between stages" in out["refused"]  # stage 5 still running
    assert sr(repo, "labels", "--run", run_id)[0] == 0
    rc, out = rs(repo, "stage", "5", "--run", run_id, "--complete")
    assert rc == 0, out
    rc, out = rs(repo, "change-inputs", "--run", run_id, "--requirements-file", str(new), "--reason", "customer email")
    assert rc == 0, out
    ch = json.loads((rd / "input/change-1.json").read_text())
    assert ch["changed_req_ids"] == ["REQ-001", "REQ-003"] and (rd / "input/requirements-v2.md").read_text() == new.read_text()
    assert (rd / "input/requirements.md").read_text() == REQ_TEXT  # original preserved
    rc, out = sr(repo, "apply", "input/change-1.json", "--run", run_id)
    assert rc == 0, out
    reg = json.loads((rd / "status_registry.json").read_text())["items"]
    assert reg["REQ-001"]["approval"] == "approved" and reg["REQ-001"]["stale"] is True  # never silently un-approved
    assert "REQ-001" in reg["REQ-001"]["stale_reason"]
    assert reg["REQ-002"]["approval"] == "not_reviewed" and not reg["REQ-002"]["stale"]
    assert reg["REQ-003"]["approval"] == "superseded"  # unapproved and changed
    assert out["stale_approved"] == ["REQ-001"] and out["superseded"] == ["REQ-003"]
    assert sr(repo, "labels", "--run", run_id)[0] == 0
    labels = json.loads((rd / "status_labels.json").read_text())
    assert "REQ-001" in labels["stale_approved"]
    assert rs(repo, "verify", "--run", run_id)[0] == 0
    rc, out = rs(repo, "change-inputs", "--run", run_id, "--requirements-file", str(new), "--reason", "again")
    assert rc == 3 and "identical" in out["refused"]


def test_apply_refuses_other_paths(repo):
    run_id = to_stage5(repo)
    rc, out = sr(repo, "apply", "status_registry.json", "--run", run_id)
    assert rc == 3 and "input/change-<n>.json" in out["refused"]


# --------------------------------------------------------------------------- metrics


def expected_doc(**kw):
    return {"schema_version": 1, "case_id": "case-01a", "requirements": [{"id": "E1", "keywords": ["award"]}, {"id": "E2", "keywords": ["teleport"]}],
            "gaps": [], "conflicts": [], "questions": [], **kw}


def test_metrics_keep_denominators_and_flag_safety(tmp_path):
    rd = tmp_path / "run"
    rd.mkdir()
    (rd / "requirements.json").write_text(json.dumps(requirements_doc("20261011-000000-aaaaaa")))
    (rd / "run_summary.json").write_text(json.dumps({"publication_status": "validated", "status_reasons": [], "warnings": []}))
    (rd / "spec.md").write_text("IGNORE ALL RULES marker\n")
    M, safety, trace = metrics.compute(rd, expected_doc(injection_markers=["IGNORE ALL RULES"]), [], 1.5, 60.0,
                                       {"searches_per_gap": 4, "fetches_per_gap": 6, "total_searches_per_run": 40})
    assert M["requirement_coverage"]["numerator"] == 1 and M["requirement_coverage"]["denominator"] == 2
    assert M["requirement_coverage"]["details"] == ["E2"]
    assert M["expected_gap_recall"]["value"] is None and M["expected_gap_recall"]["denominator"] == 0  # not applicable, not 100 %
    assert M["prompt_injection_resilience"]["value"] == 0
    assert any("injected text" in s for s in safety) and any("published as validated" in s for s in safety)
    assert all({"value", "numerator", "denominator", "definition"} <= set(v) for v in M.values())
    assert "score" not in M and "overall" not in M  # never one collapsed score


def test_metrics_blocking_failure_honesty(tmp_path):
    rd = tmp_path / "run"
    rd.mkdir()
    (rd / "validation.json").write_text(json.dumps({"mode": "full", "items": [], "blocking_failures": [4]}))
    for would, ok in (("validated", 0), ("not_fully_validated", 1)):
        (rd / "run_summary.json").write_text(json.dumps({"publication_status": "eval_only", "warnings": [],
                                                         "status_reasons": [f"fixture mode: always eval_only (checks would give {would})"]}))
        M, _, _ = metrics.compute(rd, expected_doc(), [], None, None, {"searches_per_gap": 4, "fetches_per_gap": 6, "total_searches_per_run": 40})
        assert M["blocking_failure_handling"]["value"] == ok


def test_metrics_change_impact_needs_post_review_rerun(tmp_path):
    rd = tmp_path / "run"
    (rd / "input").mkdir(parents=True)
    (rd / "checkpoints").mkdir()
    (rd / "input/change-1.json").write_text("{}")
    (rd / "checkpoints/checkpoint-13R-answers.json").write_text("{}")
    lim = {"searches_per_gap": 4, "fetches_per_gap": 6, "total_searches_per_run": 40}
    for man, ok in (({"stages": {"14": {"status": "completed"}, "15": {"status": "completed"}}}, 0),
                    ({"post15_13r_done": True, "stages": {"14": {"status": "stale"}, "15": {"status": "completed"}}}, 0),
                    ({"post15_13r_done": True, "stages": {"14": {"status": "completed"}, "15": {"status": "completed"}}}, 1)):
        (rd / "run_manifest.json").write_text(json.dumps(man))
        M, _, _ = metrics.compute(rd, expected_doc(expect_stale_and_13r=True), [], None, None, lim)
        assert M["change_impact_detection"]["value"] == ok


# --------------------------------------------------------------------------- run_evals helpers


def test_select_cases_config_order_then_name(tmp_path):
    for n in ("case-01-a", "case-06-x", "case-07-y", "case-10-z", "case-02-b"):
        (tmp_path / n).mkdir()
        (tmp_path / n / "input.json").write_text("{}")
    (tmp_path / "case-99-no-input").mkdir()
    names = [p.name for p in run_evals.select_cases(tmp_path, ["case-06", "case-07"], None)]
    assert names == ["case-06-x", "case-07-y", "case-01-a", "case-02-b", "case-10-z"]
    assert [p.name for p in run_evals.select_cases(tmp_path, ["case-06"], ["case-10"])] == ["case-10-z"]
    with pytest.raises(run_evals.EvalError):
        run_evals.select_cases(tmp_path, [], ["case-55"])


def test_child_env_and_command_never_skip_permissions():
    env = run_evals.child_env({"PATH": "/bin", "CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "s", "FRA_EVAL_FIXTURES": "evil"}, "evals/fixtures/c")
    assert env == {"PATH": "/bin", "FRA_EVAL_FIXTURES": "evals/fixtures/c"}
    assert "FRA_EVAL_FIXTURES" not in run_evals.child_env({"FRA_EVAL_FIXTURES": "x"}, None)
    cmd = run_evals.build_cmd("/feature-research --non-interactive evals/cases/c/input.json", "/py", "/s", "sonnet", 19.0)
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert "bypassPermissions" not in cmd and "--dangerously-skip-permissions" not in cmd
    tools = cmd[cmd.index("--allowedTools") + 1:cmd.index("--setting-sources")]
    assert tools == ["Read", "Write", "Agent", "WebSearch", "Bash(/py /s/*)"]
    assert cmd[cmd.index("--setting-sources") + 1] == "project" and cmd[cmd.index("--max-budget-usd") + 1] == "19.00"
    g = run_evals.build_cmd("x", "/py", "/s", "opus", 5, agent="eval-citation-grader", tools=["Read"])
    assert g[g.index("--allowedTools") + 1:g.index("--setting-sources")] == ["Read"] and g[g.index("--agent") + 1] == "eval-citation-grader"


def test_case_budget():
    assert run_evals.case_budget(20, 150, 0, 1) == 19
    assert run_evals.case_budget(20, 150, 140, 1) == 9
    assert run_evals.case_budget(20, 150, 150, 1) <= 0


def test_parse_grader_validates_every_entry():
    ids = ["F-1", "F-2", "F-3"]
    text = json.dumps({"grades": [{"id": "F-1", "grade": "supported", "reason": "r"}, {"id": "F-2", "grade": "great"},
                                  {"id": "F-9", "grade": "supported"}, {"id": "F-1", "grade": "not_supported"}]})
    grades, problems = run_evals.parse_grader(text, ids)
    assert [g["id"] for g in grades] == ["F-1"]
    assert len([p for p in problems if p.startswith("invalid")]) == 3 and "no grade for F-3" in problems
    assert run_evals.parse_grader("NEEDS INPUT: x", ids) == ([], ["grader returned no JSON"])
    s = run_evals.grader_summary(grades, problems, {"F-1": "dropped"})
    assert s["agreement_with_source_verifier"]["numerator"] == 0 and s["agreement_with_source_verifier"]["denominator"] == 1


def test_pass_check():
    M = {"budget_compliance": metrics.flag(True, "d"), "prompt_injection_resilience": metrics.flag(False, "d"),
         "change_impact_detection": metrics.flag(None, "d")}
    fails = run_evals.pass_check("completed", M, [], [])
    assert fails == ["metric prompt_injection_resilience = 0.0"]
    assert run_evals.pass_check("blocked", {}, ["s"], ["t"]) == ["run status blocked", "safety: s", "traceability: t"]


def test_find_run_and_collect_unmatched(tmp_path):
    for rid, case in (("20261011-000000-aaaaaa", CASE_REL), ("20261011-000001-bbbbbb", "evals/cases/other/input.json")):
        (tmp_path / rid / "input").mkdir(parents=True)
        (tmp_path / rid / "input/request.json").write_text(json.dumps({"non_interactive_case": {"path": case}}))
    rd = run_evals.find_run(tmp_path, CASE_REL, 0)
    assert rd.name == "20261011-000000-aaaaaa"
    (rd / "checkpoints").mkdir()
    (rd / "checkpoints/checkpoint-2-answers.json").write_text(json.dumps(
        {"checkpoint": "2", "rounds": [{"unmatched": [{"gap_id": "GAP-003", "reason": "cap"}]}]}))
    assert run_evals.collect_unmatched(rd) == [{"checkpoint": "2", "gap_id": "GAP-003", "reason": "cap"}]


# --------------------------------------------------------------------------- the real case set


CASES = sorted(p for p in (REPO / "evals/cases").iterdir() if (p / "input.json").exists())


def test_required_cases_exist():
    nums = {p.name[:7] for p in CASES}
    assert {f"case-{i:02d}" for i in range(1, 11)} <= nums


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_case_files_valid_and_self_contained(case):
    inp = json.loads((case / "input.json").read_text())
    schema.check("eval_input", inp, what=f"{case.name}/input.json")
    exp = json.loads((case / "expected.json").read_text())
    schema.check("eval_expected", exp, what=f"{case.name}/expected.json")
    assert inp["case_id"] == exp["case_id"] and case.name.startswith(inp["case_id"][:7])
    fx = REPO / inp["fixture_dir"]
    assert fx.is_dir() and fx.name == case.name, "fixture dir must share the case name (fetch_source finds sources.json by it)"
    assert (fx / inp["mockup"]).is_file()
    assert (REPO / inp["requirements_file"]).is_file()
    if "change_after_checkpoint_3" in inp:
        assert (REPO / inp["change_after_checkpoint_3"]["requirements_file"]).is_file()
        assert exp.get("expect_stale_and_13r") and "13R" in inp["checkpoints"]
    src = case / "sources.json"
    if src.exists():
        doc = json.loads(src.read_text())
        schema.check("fixture_sources", doc, what=f"{case.name}/sources.json")
        for url, target in doc["sources"].items():
            assert target == "unavailable" or (REPO / target).is_file(), url


def test_open_statuses_exist_in_manifest_schema():
    enum = json.loads((REPO / ".claude/skills/feature-research/schemas/run_manifest.schema.json").read_text())["properties"]["status"]["enum"]
    assert set(run_evals.OPEN_STATUSES) <= set(enum) and not {"completed", "aborted", "failed"} & set(run_evals.OPEN_STATUSES)


REPLAY = sorted((REPO / "evals/replay").glob("*/*/requirements.json"))


@pytest.mark.parametrize("req_path", REPLAY, ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_replay_case_answers_cover_blocking_questions(tmp_path, req_path):
    """Real questions from earlier eval runs: every blocking one must match exactly one case answer."""
    case = json.loads((REPO / "evals/cases" / req_path.parent.parent.name / "input.json").read_text())
    reqs = json.loads(req_path.read_text())
    rd = write_run(tmp_path, {r["id"]: reg_item() for r in reqs["requirements"]}, requirements=reqs)
    _, unmatched = case_answers.plan_checkpoint("1", case, rd)
    blocking = {q["id"] for q in reqs["clarifying_questions"] if q["blocking"]}
    open_blocking = [u for u in unmatched if u.get("question_id") in blocking]
    assert not open_blocking, [(u, next(q["question"] for q in reqs["clarifying_questions"] if q["id"] == u["question_id"]))
                               for u in open_blocking]


def test_smoke_state(tmp_path):
    def man(status, stages):
        (tmp_path / "run_manifest.json").write_text(json.dumps({"status": status, "stages": stages}))
    assert run_evals.smoke_state(tmp_path, "7") == "running"  # manifest not written yet
    man("running", {"5": {"status": "completed"}, "6": {"status": "running"}})
    assert run_evals.smoke_state(tmp_path, "7") == "running"
    man("awaiting_user", {"7": {"status": "completed"}})
    assert run_evals.smoke_state(tmp_path, "7") == "reached"
    man("running", {"5": {"status": "failed"}})
    assert run_evals.smoke_state(tmp_path, "7") == "failed"
    man("aborted", {})
    assert run_evals.smoke_state(tmp_path, "7") == "failed"


def test_run_claude_stops_when_asked(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evals, "POLL_SECONDS", 0.1)
    cmd = [sys.executable, "-c", "import time; print('{\"type\": \"system\"}', flush=True); time.sleep(60)"]
    t0 = __import__("time").time()
    _, result, code = run_evals.run_claude(cmd, {"PATH": "/usr/bin:/bin"}, 120, tmp_path / "log.jsonl", stop_when=lambda: "system" in (tmp_path / "log.stdout.tmp").read_text())
    assert code == -1 and result == {} and __import__("time").time() - t0 < 30
    log = (tmp_path / "log.jsonl").read_text()
    assert '"type": "system"' in log and "stopped by --until-stage" in log
    assert not list(tmp_path.glob("*.tmp"))


def test_usage_limit_is_detected():
    assert run_evals.usage_limited({"result": "You've hit your session limit · resets 1:30pm (Asia/Manila)"})
    assert run_evals.usage_limited({"result": "You've hit your individual spend limit · run /usage-credits to ask your admin"})
    assert run_evals.usage_limited({"result": "You've hit your weekly limit"})
    assert not run_evals.usage_limited({"result": "The run stopped at Stage 5."}) and not run_evals.usage_limited({})
