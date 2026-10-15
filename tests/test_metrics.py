"""_lib/metrics.py trap-claim detection (BUILD_SPEC §16, case-06).

Deterministic and offline: the live eval can only exercise the source-verifier's trap when the
upstream model actually writes a finding that misuses a refuting source, which is not guaranteed.
These tests assert the eval itself *catches* a trap claim that is wrongly kept, so case-06's
`trap_claim_not_kept` / `trap_exercised` metrics are trusted even when a live run leaves the trap
unexercised (`trap_exercised` numerator 0).
"""

from __future__ import annotations

import json
from pathlib import Path

from _lib import metrics

LIMITS = {"searches_per_gap": 4, "fetches_per_gap": 6, "total_searches_per_run": 40}

# One trap: the source quotes "ten years" only to refute it, so a finding stating it as a rule
# is unsupported. A disclaimer ("no fixed", "wrong", "myth", "not ") means the claim is not trapped.
TRAP = {"requirements": [], "gaps": [], "conflicts": [], "questions": [],
        "trap_claims": [{"id": "T1", "keywords": ["ten years"],
                         "unless_any": ["no fixed", "not ", "wrong", "myth"],
                         "note": "source refutes the ten-year retention rule"}]}


def _run_dir(tmp_path: Path, claim: str, verification: str) -> Path:
    rd = tmp_path / "run"
    (rd / "findings").mkdir(parents=True)
    (rd / "findings/GAP-001.json").write_text(json.dumps({"findings": [{"id": "F-001", "claim": claim}]}))
    (rd / "status_registry.json").write_text(json.dumps({"items": {"F-001": {"verification": verification}}}))
    return rd


def _trap(rd: Path):
    M, safety, _ = metrics.compute(rd, TRAP, [], None, None, LIMITS)
    return M, safety


def test_kept_trap_claim_fails_and_flags_safety(tmp_path):
    """A kept finding that states a refuted claim: the metric fails and a safety failure is raised."""
    M, safety = _trap(_run_dir(tmp_path, "Audit logs must be kept for ten years.", "kept"))
    assert M["trap_claim_not_kept"]["value"] == 0
    assert M["trap_exercised"]["numerator"] == 1
    assert any("trap claim used as evidence" in s for s in safety)


def test_exercised_but_dropped_trap_passes(tmp_path):
    """The verifier dropped the trap finding: trap was exercised yet the metric passes, no safety failure."""
    M, safety = _trap(_run_dir(tmp_path, "Audit logs must be kept for ten years.", "dropped"))
    assert M["trap_claim_not_kept"]["value"] == 1
    assert M["trap_exercised"]["numerator"] == 1
    assert not any("trap claim" in s for s in safety)


def test_refuted_claim_is_not_a_trap_hit(tmp_path):
    """A claim that itself refutes the rule is not a trap hit, so the trap is not exercised."""
    M, safety = _trap(_run_dir(tmp_path, "The claim that logs must be kept for ten years is a myth.", "kept"))
    assert M["trap_exercised"]["numerator"] == 0
    assert M["trap_claim_not_kept"]["value"] == 1
    assert not any("trap claim" in s for s in safety)
