"""Run mode resolution (BUILD_SPEC §16, Fixture mode). Stdlib only.

Fixture mode is enabled only by FRA_EVAL_FIXTURES in the process environment, and only
when it resolves to a directory inside evals/fixtures/. Nothing else can enable it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import paths

ENV_VAR = "FRA_EVAL_FIXTURES"
NORMAL = "normal"
FIXTURE = "fixture"


class ModeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Mode:
    mode: str
    fixture_dir: Path | None

    def as_record(self, repo: Path) -> dict:
        return {
            "mode": self.mode,
            "fixture_dir": (
                self.fixture_dir.relative_to(repo.resolve()).as_posix() if self.fixture_dir else None
            ),
        }


def resolve_mode(repo: Path, env: Mapping[str, str] | None = None) -> Mode:
    env = os.environ if env is None else env
    raw = env.get(ENV_VAR)
    if raw is None:
        return Mode(NORMAL, None)
    if not raw.strip():
        raise ModeError(f"{ENV_VAR} is set but empty")
    root = (repo / paths.FIXTURES_REL).resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repo / candidate
    resolved = candidate.resolve()
    if resolved == root or root not in resolved.parents:
        raise ModeError(f"{ENV_VAR} must name a directory inside {paths.FIXTURES_REL}/, got {raw!r}")
    if not resolved.is_dir():
        raise ModeError(f"{ENV_VAR} directory does not exist: {raw!r}")
    return Mode(FIXTURE, resolved)


def hook_runs_root(repo: Path, env: Mapping[str, str] | None = None) -> Path:
    """Hooks choose the run root by the variable's presence alone (§11.3, Run root)."""
    env = os.environ if env is None else env
    return paths.runs_root(repo, FIXTURE if ENV_VAR in env else NORMAL)
