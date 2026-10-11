"""Fixture-mode activation, config restrictions and schema sanity (BUILD_SPEC §5, §12, §16)."""

from __future__ import annotations

import copy
import json
import os

import pytest
import yaml
from jsonschema import Draft202012Validator

from _lib import modes, paths, schema
from conftest import SKILL


def test_normal_mode_without_variable(repo):
    assert modes.resolve_mode(repo, {}).mode == "normal"


def test_fixture_mode_inside_fixtures(repo):
    m = modes.resolve_mode(repo, {"FRA_EVAL_FIXTURES": "evals/fixtures/case-a"})
    assert m.mode == "fixture" and m.fixture_dir == (repo / "evals/fixtures/case-a").resolve()


@pytest.mark.parametrize("value", ["", "evals/fixtures", "evals/cases/case-a", "/tmp", "evals/fixtures/../cases",
                                   "evals/fixtures/missing"])
def test_fixture_dir_outside_or_invalid_is_rejected(repo, value):
    with pytest.raises(modes.ModeError):
        modes.resolve_mode(repo, {"FRA_EVAL_FIXTURES": value})


def test_symlink_escaping_fixtures_is_rejected(repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, repo / "evals/fixtures/link")
    with pytest.raises(modes.ModeError):
        modes.resolve_mode(repo, {"FRA_EVAL_FIXTURES": "evals/fixtures/link"})


def test_hook_run_root_follows_variable_presence(repo):
    assert modes.hook_runs_root(repo, {}) == repo / "runs"
    assert modes.hook_runs_root(repo, {"FRA_EVAL_FIXTURES": "anything"}) == repo / "evals/runs"


def _config():
    return yaml.safe_load((SKILL / "config.yaml").read_text())


def test_shipped_config_is_valid():
    assert schema.errors("config", _config()) == []


@pytest.mark.parametrize("path,key,value", [
    ((), "fixture_mode", True),
    ((), "non_interactive", True),
    ((), "python", "/usr/bin/python3"),
    ((), "interpreter", "/tmp/py"),
    ((), "disable_hooks", True),
    ((), "skip_schema_validation", True),
    (("network",), "allow_private_networks", True),
    (("network",), "verify_tls", False),
    (("capture",), "fixture_dir", "evals/fixtures/x"),
    (("research",), "skip_citation_check", True),
    (("review",), "mark_passed_on_retry_limit", True),
    (("run",), "tamper_detection", False),
    (("logging",), "log_secrets", True),
])
def test_config_rejects_safety_and_mode_keys(path, key, value):
    cfg = _config()
    target = cfg
    for p in path:
        target = target[p]
    target[key] = value
    assert schema.errors("config", cfg), f"{'.'.join(path + (key,))} should be rejected"


@pytest.mark.parametrize("path,value", [
    (("network", "allowed_schemes"), ["http", "file"]),
    (("network", "allowed_schemes"), ["ftp"]),
    (("review", "revision_rounds"), 5),
    (("review", "stage_retries"), 3),
    (("evals", "per_case_budget_usd"), 21),
    (("evals", "per_run_budget_usd"), 151),
    (("capture", "max_pages"), 10000),
])
def test_config_limits_cannot_be_widened(path, value):
    cfg = _config()
    cfg[path[0]][path[1]] = value
    assert schema.errors("config", cfg)


def test_every_schema_is_valid_and_versioned():
    for f in sorted((SKILL / "schemas").glob("*.schema.json")):
        doc = json.loads(f.read_text())
        Draft202012Validator.check_schema(doc)
        if f.name not in ("common.schema.json", "status_change.schema.json"):  # shared defs; embedded entries
            assert "schema_version" in json.dumps(doc), f.name


def _inventory():
    ref = [{"artifact": "capture/screenshots/page-001.png", "locator": "PAGE-001"}]
    return {
        "schema_version": 1, "run_id": "20261011-120000-abcdef", "capture_status": "complete",
        "screens": [{"id": "SCR-001", "provenance": "mockup_observation", "kind": "observation",
                     "evidence_refs": ref, "name": "Packages", "purpose": "Lists packages",
                     "component_ids": ["SCR-002"], "observed_states": []}],
        "components": [{"id": "SCR-002", "provenance": "mockup_observation", "kind": "observation",
                        "evidence_refs": ref, "screen_id": "SCR-001", "type": "button", "label": "Award Package",
                        "fields": [], "actions": [{"label": "Award Package"}]}],
        "flows": [], "data_entities": [],
        "ambiguous_behaviours": [{"element_ref": "SCR-002", "unanswered": ["Who can award?"], "evidence_refs": ref}],
        "limitations": [],
    }


def test_valid_inventory_passes():
    assert schema.errors("inventory", _inventory()) == []


@pytest.mark.parametrize("field,value", [("approval", "approved"), ("issues", ["unknown"]),
                                         ("verification", "kept"), ("stale", True)])
def test_inventory_forbids_status_fields(field, value):
    inv = _inventory()
    inv["components"][0][field] = value
    assert schema.errors("inventory", inv)


def test_inventory_requires_evidence_and_observation_provenance():
    inv = _inventory()
    inv["components"][0]["evidence_refs"] = []
    assert schema.errors("inventory", inv)
    inv = _inventory()
    inv["screens"][0]["provenance"] = "inference"
    assert schema.errors("inventory", inv)
    inv = _inventory()
    inv["screens"][0]["evidence_refs"][0]["artifact"] = "../../etc/passwd"
    assert schema.errors("inventory", inv)
