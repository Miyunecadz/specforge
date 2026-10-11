"""run_state.py: lifecycle, refusals, mode agreement and tamper detection (BUILD_SPEC §4, §5, §10, §16)."""

from __future__ import annotations

import base64
import json
import shutil

import pytest

import run_state
from _lib import hashing
from conftest import (OTHER_SESSION, SESSION, add_subagent_event, attest_for, env_for, run_cli, script_argv,
                      start_run)

FX = "evals/fixtures/case-a"


def rs(repo, *args, session=SESSION, fixture=None):
    return run_cli(run_state.main, script_argv(repo, "run_state", *args), repo, env_for(session, fixture))


def start_argv(repo, *extra, url="https://mockup.example.com/", text="Req"):
    return script_argv(repo, "run_state", "start", "--mockup-url", url,
                       "--requirements-b64", base64.b64encode(text.encode()).decode(), *extra)


# --------------------------------------------------------------------------- start refusals


def test_start_requires_hook_attestation(repo):
    rc, out = run_cli(run_state.main, start_argv(repo), repo, env_for())
    assert rc == 3 and "hooks are not active" in out["refused"]


def test_start_rejects_attestation_for_a_different_command(repo):
    attest_for(repo, start_argv(repo, text="other"))
    rc, out = run_cli(run_state.main, start_argv(repo), repo, env_for())
    assert rc == 3 and "exact command" in out["refused"]


def test_start_rejects_attestation_from_another_session(repo):
    argv = start_argv(repo)
    attest_for(repo, argv, session=OTHER_SESSION)
    rc, out = run_cli(run_state.main, argv, repo, env_for())
    assert rc == 3 and "different session" in out["refused"]


def test_start_requires_session_id(repo):
    argv = start_argv(repo)
    attest_for(repo, argv)
    rc, out = run_cli(run_state.main, argv, repo, env_for(session=None))
    assert rc == 3 and "CLAUDE_CODE_SESSION_ID" in out["refused"]


def test_start_requires_setup(repo):
    (repo / ".claude/feature-research.local.json").unlink()
    argv = start_argv(repo)
    attest_for(repo, argv)
    rc, out = run_cli(run_state.main, argv, repo, env_for())
    assert rc == 3 and "install_agents.py" in out["refused"]


def test_non_interactive_refused_in_normal_mode(repo):
    (repo / "evals/cases/case-a/input.json").write_text("{}")
    argv = start_argv(repo, "--non-interactive", "evals/cases/case-a/input.json")
    attest_for(repo, argv)
    rc, out = run_cli(run_state.main, argv, repo, env_for())
    assert rc == 3 and "fixture mode" in out["refused"]
    assert not (repo / "runs/.active_run").exists()


def test_non_interactive_case_file_must_be_inside_cases(repo, tmp_path):
    (tmp_path / "answers.json").write_text("{}")
    argv = start_argv(repo, "--non-interactive", str(tmp_path / "answers.json"), url="index.html")
    attest_for(repo, argv, mode="fixture")
    rc, out = run_cli(run_state.main, argv, repo, env_for(fixture=FX))
    assert rc == 3 and "evals/cases" in out["refused"]


def test_non_interactive_allowed_in_fixture_mode(repo):
    (repo / "evals/cases/case-a/input.json").write_text("{}")
    argv = start_argv(repo, "--non-interactive", "evals/cases/case-a/input.json", url="index.html")
    attest_for(repo, argv, mode="fixture")
    rc, out = run_cli(run_state.main, argv, repo, env_for(fixture=FX))
    assert rc == 0, out
    req = json.loads((repo / "evals/runs" / out["run_id"] / "input/request.json").read_text())
    assert req["non_interactive_case"]["path"] == "evals/cases/case-a/input.json"


def test_fixture_dir_outside_fixtures_refused(repo):
    argv = start_argv(repo)
    rc, out = run_cli(run_state.main, argv, repo, env_for(fixture="evals/cases/case-a"))
    assert rc == 3 and "inside evals/fixtures" in out["refused"]


def test_second_start_refused_while_a_run_is_active(repo):
    start_run(repo)
    argv = start_argv(repo, text="again")
    attest_for(repo, argv)
    rc, out = run_cli(run_state.main, argv, repo, env_for())
    assert rc == 3 and "another run is active" in out["refused"]


# --------------------------------------------------------------------------- start outputs


def test_start_preserves_inputs_and_writes_active_run(repo, tmp_path):
    req_file = tmp_path / "req.md"
    req_file.write_text("It's a \"quoted\" requirement — with ünïcode.\nSecond line.")
    argv = script_argv(repo, "run_state", "start", "--mockup-url", "https://m.example/", "--requirements-file",
                       str(req_file))
    attest_for(repo, argv)
    rc, out = run_cli(run_state.main, argv, repo, env_for())
    assert rc == 0, out
    run_dir = repo / "runs" / out["run_id"]
    assert (run_dir / "input/requirements.md").read_bytes() == req_file.read_bytes()
    req = json.loads((run_dir / "input/request.json").read_text())
    assert req["requirements"]["sha256"] == hashing.sha256_file(req_file)
    assert req["mode"] == "normal" and req["declared_input_type"] == "html"
    active = json.loads((repo / "runs/.active_run").read_text())
    assert active["run_id"] == out["run_id"] and active["session_id"] == SESSION and active["mode"] == "normal"
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert manifest["stages"]["1"]["status"] == "running" and manifest["publication_status"] is None
    assert (run_dir / "input/config.yaml").exists()
    assert hashing.verify_chain(run_dir / "log.jsonl") == []


def test_fixture_run_uses_its_own_root_and_is_eval_only(repo):
    run_id = start_run(repo, url="index.html", fixture=FX)
    assert (repo / "evals/runs/.active_run").exists()
    assert not (repo / "runs/.active_run").exists()
    m = json.loads((repo / "evals/runs" / run_id / "run_manifest.json").read_text())
    assert m["mode"] == "fixture" and m["fixture_dir"] == FX and m["publication_status"] == "eval_only"


# --------------------------------------------------------------------------- refusals on existing runs


def test_scripts_refuse_on_mode_mismatch(repo):
    run_id = start_run(repo)
    rc, out = rs(repo, "verify", "--run", run_id, fixture=FX)
    assert rc == 3  # fixture environment cannot see or act on a normal run


def test_scripts_refuse_other_session(repo):
    run_id = start_run(repo)
    rc, out = rs(repo, "verify", "--run", run_id, session=OTHER_SESSION)
    assert rc == 3 and "another Claude Code session" in out["refused"]


def test_manifest_mode_tampering_is_refused(repo):
    run_id = start_run(repo)
    mpath = repo / "runs" / run_id / "run_manifest.json"
    m = json.loads(mpath.read_text())
    m["mode"] = "fixture"
    mpath.write_text(json.dumps(m))
    rc, out = rs(repo, "verify", "--run", run_id)
    assert rc == 3 and "mode mismatch" in out["refused"]


def test_later_phase_subcommands_are_refused(repo):
    run_id = start_run(repo)
    for cmd in ("await-user", "continue", "resume", "set-gap", "report"):
        rc, out = rs(repo, cmd, "--run", run_id)
        assert rc == 3 and "Phase" in out["refused"]


# --------------------------------------------------------------------------- stages


def test_stage_flow_and_ordering(repo):
    run_id = start_run(repo)
    assert rs(repo, "stage", "3", "--run", run_id, "--start")[0] == 3  # stage 2 not done
    assert rs(repo, "stage", "1", "--run", run_id, "--complete")[0] == 0
    assert rs(repo, "stage", "2", "--run", run_id, "--start")[0] == 0
    rc, out = rs(repo, "stage", "2", "--run", run_id, "--complete")
    assert rc == 1 and any("missing output" in e for e in out["errors"])
    assert rs(repo, "stage", "4", "--run", run_id, "--start")[0] == 3  # not implemented in Phase 1a


def _capture_manifest(run_id, status="complete"):
    return {"schema_version": 1, "run_id": run_id, "method": "html", "mode": "normal", "fixture_dir": None,
            "captured_at": "2026-10-11T00:00:00.000Z", "original_url": "https://m.example/", "status": status,
            "pages": [{"id": "PAGE-001", "url": "https://m.example/", "final_url": "https://m.example/",
                       "title": "t", "depth": 0, "status": "captured", "http_status": 200,
                       "screenshot": "capture/screenshots/page-001.png", "text": "capture/pages/page-001.txt",
                       "aria": None, "html": None, "nav_labels": [], "error": None}],
            "frames": [], "assets": [], "links": [], "blocked_requests": [], "failed_requests": [],
            "warnings": [], "limitations": [], "access_failures": [], "limits": {},
            "totals": {"pages_captured": 1, "pages_failed": 0, "pages_skipped": 0, "frames_captured": 0,
                       "frames_failed": 0, "frames_skipped": 0, "bytes": 1,
                       "requests_blocked": 0}}


def _fake_capture(repo, run_id):
    cap = repo / "runs" / run_id / "capture"
    (cap / "screenshots").mkdir(parents=True)
    (cap / "pages").mkdir()
    (cap / "screenshots/page-001.png").write_bytes(b"png")
    (cap / "pages/page-001.txt").write_text("Award Package")
    (cap / "manifest.json").write_text(json.dumps(_capture_manifest(run_id)))


def _inventory(run_id, status="complete"):
    ref = [{"artifact": "capture/screenshots/page-001.png", "locator": "PAGE-001"}]
    return {"schema_version": 1, "run_id": run_id, "capture_status": status,
            "screens": [{"id": "SCR-001", "provenance": "mockup_observation", "kind": "observation",
                         "evidence_refs": ref, "name": "Packages", "purpose": "Lists packages",
                         "component_ids": [], "observed_states": []}],
            "components": [], "flows": [], "data_entities": [], "ambiguous_behaviours": [], "limitations": []}


def _through_stage2(repo):
    run_id = start_run(repo)
    assert rs(repo, "stage", "1", "--run", run_id, "--complete")[0] == 0
    assert rs(repo, "stage", "2", "--run", run_id, "--start")[0] == 0
    _fake_capture(repo, run_id)
    assert rs(repo, "stage", "2", "--run", run_id, "--complete")[0] == 0
    return run_id


def test_agent_stage_requires_recorded_subagent(repo):
    run_id = _through_stage2(repo)
    assert rs(repo, "stage", "3", "--run", run_id, "--start")[0] == 0
    (repo / "runs" / run_id / "inventory.json").write_text(json.dumps(_inventory(run_id)))
    rc, out = rs(repo, "stage", "3", "--run", run_id, "--complete")
    assert rc == 1 and any("subagent invocation" in e for e in out["errors"])
    add_subagent_event(repo, run_id, "doc-writer")  # the wrong agent does not count
    assert rs(repo, "stage", "3", "--run", run_id, "--complete")[0] == 1
    add_subagent_event(repo, run_id, "mockup-extractor")
    rc, out = rs(repo, "stage", "3", "--run", run_id, "--complete")
    assert rc == 0, out


def test_inventory_semantic_checks(repo):
    run_id = _through_stage2(repo)
    assert rs(repo, "stage", "3", "--run", run_id, "--start")[0] == 0
    add_subagent_event(repo, run_id, "mockup-extractor")
    inv = _inventory(run_id, status="partial")  # capture said complete
    inv["screens"][0]["evidence_refs"][0]["artifact"] = "capture/screenshots/page-009.png"
    (repo / "runs" / run_id / "inventory.json").write_text(json.dumps(inv))
    rc, out = rs(repo, "stage", "3", "--run", run_id, "--complete")
    assert rc == 1
    joined = " ".join(out["errors"])
    assert "capture_status" in joined and "page-009.png" in joined


def test_invalid_output_fails_schema_validation(repo):
    run_id = _through_stage2(repo)
    assert rs(repo, "stage", "3", "--run", run_id, "--start")[0] == 0
    inv = _inventory(run_id)
    inv["screens"][0]["approval"] = "approved"
    (repo / "runs" / run_id / "inventory.json").write_text(json.dumps(inv))
    rc, out = rs(repo, "stage", "3", "--run", run_id, "--complete")
    assert rc == 1 and any("inventory.json" in e for e in out["errors"])


# --------------------------------------------------------------------------- tamper detection


def test_legitimate_writes_never_trigger_tamper(repo):
    run_id = _through_stage2(repo)
    for _ in range(3):
        rc, out = rs(repo, "verify", "--run", run_id)
        assert rc == 0, out
    add_subagent_event(repo, run_id, "mockup-extractor")
    rc, out = rs(repo, "verify", "--run", run_id)
    assert rc == 0, out


@pytest.mark.parametrize("mutate,expect", [
    ("input", "input/requirements.md"),
    ("capture", "capture/pages/page-001.txt"),
    ("capture_add", "capture/pages/extra.txt"),
    ("manifest", "run_manifest.json"),
    ("log_edit", "log.jsonl"),
    ("log_truncate", "run_manifest.json"),
    ("unowned", "notes.txt"),
    ("active_run", ".active_run"),
    ("hook_events", ".hook_events.jsonl"),
])
def test_tamper_is_detected(repo, mutate, expect):
    run_id = _through_stage2(repo)
    add_subagent_event(repo, run_id, "mockup-extractor")
    assert rs(repo, "verify", "--run", run_id)[0] == 0
    run_dir = repo / "runs" / run_id
    if mutate == "input":
        (run_dir / "input/requirements.md").write_text("changed")
    elif mutate == "capture":
        (run_dir / "capture/pages/page-001.txt").write_text("changed")
    elif mutate == "capture_add":
        (run_dir / "capture/pages/extra.txt").write_text("new")
    elif mutate == "manifest":
        m = json.loads((run_dir / "run_manifest.json").read_text())
        m["current_stage"] = "9"
        (run_dir / "run_manifest.json").write_text(json.dumps(m))
    elif mutate == "log_edit":
        lines = (run_dir / "log.jsonl").read_text().splitlines()
        rec = json.loads(lines[0])
        rec["detail"]["mockup_url"] = "https://evil.example/"
        lines[0] = json.dumps(rec)
        (run_dir / "log.jsonl").write_text("\n".join(lines) + "\n")
    elif mutate == "log_truncate":
        lines = (run_dir / "log.jsonl").read_text().splitlines()
        (run_dir / "log.jsonl").write_text("\n".join(lines[:-3]) + "\n")
    elif mutate == "unowned":
        (run_dir / "notes.txt").write_text("hello")
    elif mutate == "active_run":
        a = json.loads((repo / "runs/.active_run").read_text())
        a["started_at"] = "2020-01-01T00:00:00.000Z"
        (repo / "runs/.active_run").write_text(json.dumps(a, indent=2) + "\n")
    elif mutate == "hook_events":
        lines = (repo / "runs/.hook_events.jsonl").read_text().splitlines()
        rec = json.loads(lines[0])
        rec["agent_type"] = "doc-writer"
        lines[0] = json.dumps(rec)
        (repo / "runs/.hook_events.jsonl").write_text("\n".join(lines) + "\n")
    rc, out = rs(repo, "verify", "--run", run_id)
    assert rc == 4, out
    files = [p["file"] for p in out["tamper"]]
    assert any(f.endswith(expect) for f in files), files
    assert all(p["owner"] for p in out["tamper"])
    # stage start refuses too
    assert rs(repo, "stage", "3", "--run", run_id, "--start")[0] == 4


# --------------------------------------------------------------------------- end and abort


def test_end_removes_active_run(repo):
    run_id = start_run(repo)
    rc, out = rs(repo, "end", "--run", run_id)
    assert rc == 0 and not (repo / "runs/.active_run").exists()
    assert rs(repo, "verify", "--run", run_id)[0] == 3


def test_abort_from_another_session_preserves_artifacts(repo):
    run_id = start_run(repo)
    files_before = sorted(p.relative_to(repo) for p in (repo / "runs" / run_id).rglob("*") if p.is_file())
    rc, out = rs(repo, "abort", "--run", run_id, "--reason", "stuck", session=OTHER_SESSION)
    assert rc == 0 and out["active_run_removed"]
    assert not (repo / "runs/.active_run").exists()
    files_after = sorted(p.relative_to(repo) for p in (repo / "runs" / run_id).rglob("*") if p.is_file())
    assert set(files_before) <= set(files_after)
    m = json.loads((repo / "runs" / run_id / "run_manifest.json").read_text())
    assert m["status"] == "aborted" and m["abort_reason"] == "stuck"
    assert rs(repo, "abort", "--run", run_id, "--reason", "again")[0] == 3
    assert rs(repo, "verify", "--run", run_id)[0] == 3


def test_abort_of_old_run_keeps_other_active_run(repo):
    first = start_run(repo)
    rs(repo, "end", "--run", first)
    second = start_run(repo, requirements="second")
    m = json.loads((repo / "runs" / first / "run_manifest.json").read_text())
    assert m["status"] == "completed"
    assert rs(repo, "abort", "--run", first, "--reason", "x")[0] == 3
    assert json.loads((repo / "runs/.active_run").read_text())["run_id"] == second
