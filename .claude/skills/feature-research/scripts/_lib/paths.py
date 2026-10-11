"""Repository-relative locations shared by scripts and hooks (stdlib only)."""

from __future__ import annotations

from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = SKILL_DIR.parents[2]

SKILL_REL = Path(".claude/skills/feature-research")
SETUP_REL = Path(".claude/feature-research.local.json")
AGENTS_REL = Path(".claude/agents")
FIXTURES_REL = Path("evals/fixtures")
CASES_REL = Path("evals/cases")

NORMAL_RUNS_REL = Path("runs")
FIXTURE_RUNS_REL = Path("evals/runs")

# Scripts H1 allows during a run (BUILD_SPEC §10, excluding install_agents and run_evals).
RUN_SCRIPTS = (
    "run_state",
    "check_url",
    "capture_mockup",
    "validate",
    "fetch_source",
    "verify_citations",
    "status_rules",
    "check_spec",
)
SETUP_ONLY_SCRIPTS = ("install_agents", "run_evals")


def skill_dir(repo: Path) -> Path:
    return repo / SKILL_REL


def scripts_dir(repo: Path) -> Path:
    return skill_dir(repo) / "scripts"


def schemas_dir(repo: Path) -> Path:
    return skill_dir(repo) / "schemas"


def setup_path(repo: Path) -> Path:
    return repo / SETUP_REL


def runs_root(repo: Path, mode: str) -> Path:
    return repo / (FIXTURE_RUNS_REL if mode == "fixture" else NORMAL_RUNS_REL)
