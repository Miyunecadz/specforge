"""Shared test fixtures. Tests never touch the real runs/ or evals/runs/ directories."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / ".claude/skills/feature-research"
SCRIPTS = SKILL / "scripts"
HOOKS = REPO / ".claude/hooks"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HOOKS))

from _lib import attest, fsutil, hashing  # noqa: E402

SESSION = "11111111-2222-3333-4444-555555555555"
OTHER_SESSION = "99999999-8888-7777-6666-555555555555"


def chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


_CHROMIUM = None


def need_chromium():
    global _CHROMIUM
    if _CHROMIUM is None:
        _CHROMIUM = chromium_available()
    if not _CHROMIUM:
        pytest.skip("BLOCKED: Chromium cannot launch (system libraries missing; run "
                    "sudo .venv/bin/playwright install-deps chromium)")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal copy of the repository layout in a temp directory."""
    root = tmp_path / "repo"
    skill = root / ".claude/skills/feature-research"
    skill.mkdir(parents=True)
    for name in ("config.yaml",):
        shutil.copy(SKILL / name, skill / name)
    for d in ("schemas", "agents-src", "references", "templates"):
        if (SKILL / d).exists():
            shutil.copytree(SKILL / d, skill / d)
        else:
            (skill / d).mkdir()
    if (SKILL / "SKILL.md").exists():
        shutil.copy(SKILL / "SKILL.md", skill / "SKILL.md")
    rules = root / ".claude/skills/feature-research-subagent-rules"
    rules.mkdir(parents=True)
    shutil.copy(REPO / ".claude/skills/feature-research-subagent-rules/SKILL.md", rules / "SKILL.md")
    (root / "evals/fixtures/case-a").mkdir(parents=True)
    (root / "evals/cases/case-a").mkdir(parents=True)
    write_setup(root)
    return root


def write_setup(root: Path, **overrides) -> dict:
    setup = {
        "schema_version": 1,
        "python": str(Path(sys.executable).absolute()),
        "repo_root": str(root),
        "skill_dir": str(root / ".claude/skills/feature-research"),
        "hook_mode": "identified",
        "session_ids": True,
        "preload_rules": False,
        "researcher_variant": "web-researcher",
        "workflow_agents": ["mockup-extractor", "requirements-parser", "gap-analyst", "web-researcher",
                            "source-verifier", "feasibility-analyst", "question-generator", "doc-writer",
                            "doc-reviewer"],
        "installed_agents": ["mockup-extractor"],
        "rules_sha256": "0" * 64,
        "agents_src_sha256": "0" * 64,
        "claude_version": "2.1.296",
        "installed_at": "2026-10-11T00:00:00.000Z",
    }
    setup.update(overrides)
    p = root / ".claude/feature-research.local.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(setup, indent=2))
    return setup


def script_argv(root: Path, name: str, *args: str) -> list[str]:
    return [str(root / ".claude/skills/feature-research/scripts" / f"{name}.py"), *args]


def attest_for(root: Path, argv: list[str], session: str = SESSION, mode: str = "normal") -> None:
    """Simulate H1 attesting a run_state.py start/resume/continue command."""
    from _common import now_iso

    rr = root / ("evals/runs" if mode == "fixture" else "runs")
    rr.mkdir(parents=True, exist_ok=True)
    hb_path = rr / ".heartbeat"
    hb = json.loads(hb_path.read_text()) if hb_path.exists() else {"schema_version": 1, "sessions": {}, "attest": None}
    hb["attest"] = {"session_id": session, "argv_sha256": attest.argv_digest(argv), "at": now_iso()}
    fsutil.atomic_write_json(hb_path, hb)


def env_for(session: str | None = SESSION, fixture: str | None = None) -> dict:
    env = {}
    if session:
        env["CLAUDE_CODE_SESSION_ID"] = session
    if fixture is not None:
        env["FRA_EVAL_FIXTURES"] = fixture
    return env


def start_run(root: Path, url: str = "https://mockup.example.com/", session: str = SESSION,
              fixture: str | None = None, requirements: str = "The manager can award a package.") -> str:
    import base64

    import run_state

    argv = script_argv(root, "run_state", "start", "--mockup-url", url,
                       "--requirements-b64", base64.b64encode(requirements.encode()).decode())
    attest_for(root, argv, session, "fixture" if fixture else "normal")
    rc, out = run_cli(run_state.main, argv, root, env_for(session, fixture))
    assert rc == 0, out
    return out["run_id"]


def run_cli(func, argv, root, env):
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = func(argv, repo=root, env=env)
    text = buf.getvalue()
    try:
        out = json.loads(text)
    except ValueError:
        out = {"raw": text}
    return rc, out


def add_subagent_event(root: Path, run_id: str, agent: str, session: str = SESSION, mode: str = "normal") -> None:
    import record_subagent

    payload = {"hook_event_name": "SubagentStart", "session_id": session, "agent_id": "a1",
               "agent_type": agent}
    env = {"FRA_EVAL_FIXTURES": "x"} if mode == "fixture" else {}
    assert record_subagent.record(payload, env, repo=root)


def chain_line(path: Path, record: dict) -> None:
    hashing.append_chained(path, record)
