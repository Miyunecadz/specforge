"""The ownership table (BUILD_SPEC §5) as classified for H2 and tamper reports."""

from __future__ import annotations

from pathlib import Path

import pytest

from _lib import ownership as o

RR = Path("/x/runs")
RUN = "20261011-120000-abcdef"

SCRIPT_OR_HOOK_PATHS = [
    (".active_run", "run_state.py", o.SCRIPT, True),
    (".heartbeat", "hooks", o.HOOK, True),
    (".hook_events.jsonl", "hooks", o.HOOK, True),
    ("run_manifest.json", "run_state.py", o.SCRIPT, False),
    ("log.jsonl", "run_state.py", o.SCRIPT, False),
    ("input/request.json", "run_state.py", o.SCRIPT, False),
    ("input/requirements.md", "run_state.py", o.SCRIPT, False),
    ("input/prior_decisions.json", "run_state.py", o.SCRIPT, False),
    ("warnings.json", "run_state.py", o.SCRIPT, False),
    ("run_summary.json", "run_state.py", o.SCRIPT, False),
    ("budget/active_gap.json", "run_state.py", o.SCRIPT, False),
    ("integrity/run_state.json", "run_state.py", o.SCRIPT, False),
    ("capture/manifest.json", "capture_mockup.py", o.SCRIPT, False),
    ("capture/screenshots/page-001.png", "capture_mockup.py", o.SCRIPT, False),
    ("checkpoints/checkpoint-1-answers.json", "status_rules.py", o.SCRIPT, False),
    ("decisions.json", "status_rules.py", o.SCRIPT, False),
    ("status_registry.json", "status_rules.py", o.SCRIPT, False),
    ("status_history.jsonl", "status_rules.py", o.SCRIPT, False),
    ("sources/SRC-0a1b2c3d.txt", "fetch_source.py", o.SCRIPT, False),
    ("sources/SRC-0a1b2c3d.metadata.json", "fetch_source.py", o.SCRIPT, False),
    ("fetch_log.jsonl", "fetch_source.py", o.SCRIPT, False),
    ("budget/fetches-GAP-001.json", "fetch_source.py", o.SCRIPT, False),
    ("budget/searches.jsonl", "hooks", o.HOOK, False),
    ("citation_check.json", "verify_citations.py", o.SCRIPT, False),
    ("validation.json", "check_spec.py", o.SCRIPT, False),
]

AGENT_PATHS = [
    ("inventory.json", "mockup-extractor"),
    ("requirements.json", "requirements-parser"),
    ("gaps.json", "gap-analyst"),
    ("findings/GAP-001.json", "web-researcher"),
    ("fetch_requests/GAP-001.json", "web-researcher-fallback"),
    ("verified_findings.json", "source-verifier"),
    ("feasibility.json", "feasibility-analyst"),
    ("questions.json", "question-generator"),
    ("spec.md", "doc-writer"),
    ("review.json", "doc-reviewer"),
    ("warnings/gap-analyst.json", "gap-analyst"),
]


@pytest.mark.parametrize("rel,owner,kind,root", SCRIPT_OR_HOOK_PATHS)
def test_script_and_hook_paths(rel, owner, kind, root):
    path = RR / rel if root else RR / RUN / rel
    c = o.classify(RR, path)
    assert (c.owner, c.kind) == (owner, kind)


@pytest.mark.parametrize("rel,owner", AGENT_PATHS)
def test_agent_paths(rel, owner):
    c = o.classify(RR, RR / RUN / rel)
    assert (c.owner, c.kind, c.run_id) == (owner, o.AGENT, RUN)


def test_lock_and_temp_files_belong_to_their_target():
    assert o.owner_of_run_path("fetch_log.jsonl.lock") == ("fetch_source.py", o.SCRIPT)
    assert o.owner_of_run_path("capture/.manifest.json.x8a9.tmp") == ("capture_mockup.py", o.SCRIPT)
    assert o.owner_of_run_path(".inventory.json.abc.tmp") == ("mockup-extractor", o.AGENT)


def test_unknown_paths_are_unowned_and_depth_is_exact():
    assert o.owner_of_run_path("notes.txt")[1] == o.UNOWNED
    assert o.owner_of_run_path("findings/sub/GAP-001.json")[1] == o.UNOWNED
    assert o.owner_of_run_path("warnings/x/y.json")[1] == o.UNOWNED
    assert o.classify(RR, Path("/elsewhere/file")).scope == "outside"


def test_agent_may_write_only_its_own_paths():
    assert o.agent_may_write("mockup-extractor", "inventory.json")
    assert o.agent_may_write("mockup-extractor", "warnings/mockup-extractor.json")
    assert not o.agent_may_write("mockup-extractor", "warnings/doc-writer.json")
    assert not o.agent_may_write("mockup-extractor", "requirements.json")
    assert not o.agent_may_write("mockup-extractor", "capture/manifest.json")
    assert o.agent_may_write("web-researcher", "findings/GAP-002.json")
    assert o.agent_may_write("web-researcher-fallback", "findings/GAP-002.json")
    assert not o.agent_may_write("web-researcher", "sources/SRC-0a1b2c3d.txt")
    assert not o.agent_may_write("web-researcher", "fetch_requests/GAP-002.json")
