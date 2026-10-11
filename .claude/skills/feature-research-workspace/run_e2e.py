#!/usr/bin/env python3
"""Run one /feature-research invocation end to end in a throwaway copy of the repository.

Usage: run_e2e.py --out DIR --prompt TEXT [--fixture evals/fixtures/<case>] [--model sonnet] [--budget 3]

The sandbox gets a copy of the repo (without .git, runs/, evals/runs/, workspaces), a
symlink to the real .venv, freshly generated agents, and project-only settings, so the
real hooks (H1, H2, H5, recorder) are active. claude -p runs with --permission-mode dontAsk
and an explicit allow list; it never skips permission checks.
"""
import argparse, json, os, shutil, subprocess, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKIP = {".git", "runs", ".venv", "feature-research-workspace", "agent-tests", "__pycache__", ".pytest_cache"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--prompt", required=True)
    ap.add_argument("--fixture"); ap.add_argument("--model", default="sonnet"); ap.add_argument("--budget", default="3")
    a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    sb = Path(tempfile.mkdtemp(prefix="fra-e2e-"))
    def ignore(d, names):
        return [n for n in names if n in SKIP or (Path(d).name == "evals" and n == "runs")]
    shutil.copytree(REPO, sb, dirs_exist_ok=True, ignore=ignore)
    os.symlink(REPO / ".venv", sb / ".venv")
    py = str(sb / ".venv/bin/python"); scripts = str(sb / ".claude/skills/feature-research/scripts")
    inst = subprocess.run([py, f"{scripts}/install_agents.py"], cwd=sb, capture_output=True, text=True)
    (out / "install.json").write_text(inst.stdout + inst.stderr)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_CODE_SESSION", "FRA_"))}
    env.pop("CLAUDECODE", None)
    if a.fixture:
        env["FRA_EVAL_FIXTURES"] = a.fixture
    allowed = ["Read", "Write", "Agent", f"Bash({py} {scripts}/*)"]
    cmd = ["claude", "-p", a.prompt, "--model", a.model, "--permission-mode", "dontAsk",
           "--allowedTools", *allowed, "--setting-sources", "project", "--max-budget-usd", str(a.budget),
           "--output-format", "stream-json", "--verbose"]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=sb, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=1800)
    (out / "transcript.jsonl").write_text(proc.stdout); (out / "stderr.txt").write_text(proc.stderr)
    events = [json.loads(l) for l in proc.stdout.splitlines() if l.strip().startswith("{")]
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    calls = []
    for e in events:
        if e.get("type") == "assistant":
            for c in e["message"].get("content", []):
                if c.get("type") == "tool_use":
                    calls.append({"tool": c["name"], "input": json.dumps(c["input"])[:300],
                                  "subagent": e.get("parent_tool_use_id") is not None})
    (out / "tool_calls.json").write_text(json.dumps(calls, indent=1))
    (out / "final.md").write_text(str(result.get("result", "")))
    metrics = {"sandbox": str(sb), "duration_s": round(time.time() - t0, 1), "cost_usd": result.get("total_cost_usd"),
               "subtype": result.get("subtype"), "is_error": result.get("is_error"), "num_turns": result.get("num_turns"),
               "exit": proc.returncode, "prompt": a.prompt, "fixture": a.fixture, "model": a.model}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics))

if __name__ == "__main__":
    main()
