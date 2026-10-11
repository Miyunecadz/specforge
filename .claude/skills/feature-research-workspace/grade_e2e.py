"""Programmatic assertions for /feature-research e2e evals. Usage: grade_e2e.py <iteration-dir>"""
import json, subprocess, sys
from pathlib import Path
it = Path(sys.argv[1])
def runs(sb, root):
    rr = sb / root
    return sorted(p for p in rr.iterdir() if p.is_dir()) if rr.exists() else []
def jl(p): return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
for d in sorted(it.glob("eval-*")):
    out = d / "with_skill/outputs"; m = json.loads((out / "metrics.json").read_text()); sb = Path(m["sandbox"])
    final = (out / "final.md").read_text(); calls = json.loads((out / "tool_calls.json").read_text())
    root = "evals/runs" if m["fixture"] else "runs"
    rs = runs(sb, root); man = json.loads((rs[0] / "run_manifest.json").read_text()) if rs else {}
    st = man.get("stages", {}); ev = jl(sb / root / ".hook_events.jsonl")
    blocks = [e for e in ev if e["event"] == "block"]; subs = [e["agent_type"] for e in ev if e["event"] == "subagent_start"]
    A = []
    def a(text, ok, evidence): A.append({"text": text, "passed": bool(ok), "evidence": str(evidence)[:400]})
    tools = sorted({c["tool"] for c in calls if not c["subagent"]})
    a("Orchestrator used only Read, Bash and Agent", set(tools) <= {"Read", "Bash", "Agent"}, tools)
    a("No hook blocks (no disallowed call attempted)", not blocks, [b["reason"] for b in blocks])
    a("No .active_run left behind", not (sb / root / ".active_run").exists(), "")
    name = d.name
    if "eval-4" in name:
        a("No run started", not rs, [p.name for p in rs])
        a("Asks for the requirements", "requirement" in final.lower(), final[:200])
    else:
        a("Exactly one run created", len(rs) == 1, [p.name for p in rs])
        a("Run aborted with a reason", man.get("status") == "aborted" and man.get("abort_reason"), man.get("abort_reason"))
        a("Stage 1 completed", st.get("1", {}).get("status") == "completed", st.get("1", {}).get("status"))
        a("Final report gives the run ID", rs and rs[0].name in final, "")
    if "eval-1" in name:
        a("Stages 2 and 3 completed", all(st.get(k, {}).get("status") == "completed" for k in ("2", "3")), {k: v["status"] for k, v in st.items()})
        r = subprocess.run([str(sb / ".venv/bin/python"), str(sb / ".claude/skills/feature-research/scripts/validate.py"), "inventory", str(rs[0] / "inventory.json")], capture_output=True, text=True)
        a("inventory.json is schema-valid", r.returncode == 0, r.stdout[:200])
        a("mockup-extractor invoked via recorded subagent", "mockup-extractor" in subs, subs)
        a("Abort reason says later stages not built", "not built" in (man.get("abort_reason") or ""), man.get("abort_reason"))
        a("Publication status eval_only", man.get("publication_status") == "eval_only", man.get("publication_status"))
    if "eval-2" in name:
        cap = json.loads((rs[0] / "capture/manifest.json").read_text()) if (rs[0] / "capture/manifest.json").exists() else {}
        ok_browser = cap.get("status") in ("complete", "partial")
        if ok_browser:
            a("Stages 2 and 3 completed (browser available)", all(st.get(k, {}).get("status") == "completed" for k in ("2", "3")), {k: v["status"] for k, v in st.items()})
        else:
            a("Stage 2 recorded failed", st.get("2", {}).get("status") == "failed", st.get("2"))
            a("No inventory produced", not (rs[0] / "inventory.json").exists(), "")
            a("Failure quoted in report, not described as inspected", "fail" in final.lower() and (cap.get("access_failures") or ["?"])[0][:40] in final, cap.get("access_failures"))
    if "eval-3" in name:
        a("No capture attempted", not (rs[0] / "capture").exists(), "")
        a("Report names blocked_address", "blocked_address" in final, final[:200])
    (d / "with_skill/grading.json").write_text(json.dumps({"expectations": A, "summary": {"passed": sum(x["passed"] for x in A), "failed": sum(not x["passed"] for x in A), "total": len(A), "pass_rate": round(sum(x["passed"] for x in A) / len(A), 2)}}, indent=2))
    (d / "with_skill/timing.json").write_text(json.dumps({"total_duration_seconds": m["duration_s"], "cost_usd": m["cost_usd"]}))
    print(d.name, f"{sum(x['passed'] for x in A)}/{len(A)}", [x["text"] for x in A if not x["passed"]])
