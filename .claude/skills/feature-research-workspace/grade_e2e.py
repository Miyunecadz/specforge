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
    if "eval-8" not in d.name:  # eval 8 may hit the search budget (H3 blocks are expected there)
        a("No hook blocks (no disallowed call attempted)", not blocks, [b["reason"] for b in blocks])
    name = d.name
    single_turn_checkpoint = any(f"eval-{n}-" in name for n in (1, 2, 5, 6))  # Phase 2: these stop at Checkpoint 1
    if single_turn_checkpoint:
        a("Run left open at Checkpoint 1, waiting for the user", man.get("status") == "awaiting_user"
          and man.get("awaiting_checkpoint") == "1" and (sb / root / ".active_run").exists(), (man.get("status"), man.get("awaiting_checkpoint")))
        a("Stages 1-4 completed", all(st.get(k, {}).get("status") == "completed" for k in "1234"), {k: v["status"] for k, v in st.items()})
        a("Checkpoint 1 presented with the dedicated-session note", "checkpoint 1" in final.lower() and "dedicated" in final.lower(), final[-200:])
    else:
        a("No .active_run left behind", not (sb / root / ".active_run").exists(), "")
    if "eval-4" in name:
        a("No run started", not rs, [p.name for p in rs])
        a("Asks for the requirements", "requirement" in final.lower(), final[:200])
    else:
        a("Exactly one run created", len(rs) == 1, [p.name for p in rs])
        if not single_turn_checkpoint:
            a("Run aborted with a reason", man.get("status") == "aborted" and man.get("abort_reason"), man.get("abort_reason"))
        a("Stage 1 completed", st.get("1", {}).get("status") == "completed", st.get("1", {}).get("status"))
        a("Final report gives the run ID", rs and rs[0].name in final, "")
    if "eval-1" in name:
        a("Stages 2 and 3 completed", all(st.get(k, {}).get("status") == "completed" for k in ("2", "3")), {k: v["status"] for k, v in st.items()})
        r = subprocess.run([str(sb / ".venv/bin/python"), str(sb / ".claude/skills/feature-research/scripts/validate.py"), "inventory", str(rs[0] / "inventory.json")], capture_output=True, text=True)
        a("inventory.json is schema-valid", r.returncode == 0, r.stdout[:200])
        a("mockup-extractor invoked via recorded subagent", "mockup-extractor" in subs, subs)
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
    if "eval-5" in name or "eval-6" in name:
        a("Stages 2 and 3 completed", all(st.get(k, {}).get("status") == "completed" for k in ("2", "3")), {k: v["status"] for k, v in st.items()})
        cap = json.loads((rs[0] / "capture/manifest.json").read_text())
        inv = json.loads((rs[0] / "inventory.json").read_text()) if (rs[0] / "inventory.json").exists() else {}
        a("mockup-extractor invoked via recorded subagent", "mockup-extractor" in subs, subs)
    if "eval-5" in name:
        a("Capture partial with failed pages and blocked requests", cap["status"] == "partial" and cap["totals"]["pages_failed"] >= 2 and cap["totals"]["requests_blocked"] >= 3, cap["totals"])
        a("Inventory labelled partial, first limitation says so", inv.get("capture_status") == "partial" and "partial" in (inv.get("limitations") or [""])[0].lower(), (inv.get("limitations") or [""])[0])
        a("Report says partial", "partial" in final.lower(), final[:200])
    if "eval-6" in name:
        a("Figma capture of 3 frames", cap["method"] == "figma" and cap["totals"]["frames_captured"] == 3, cap["totals"])
        a("Inventory has 3 screens", len(inv.get("screens", [])) == 3, len(inv.get("screens", [])))
    if "eval-7" in name:
        import unicodedata
        norm = lambda t: " ".join(unicodedata.normalize("NFC", t).split())
        a("Stages 1-7 completed", all(st.get(k, {}).get("status") == "completed" for k in "1234567"), {k: v["status"] for k, v in st.items()})
        decs = json.loads((rs[0] / "decisions.json").read_text())["decisions"] if (rs[0] / "decisions.json").exists() else []
        turns = json.loads((out / "turns.json").read_text())
        typed = [norm(t["prompt"]) for t in turns[1:]]
        a("Decisions recorded at checkpoints 1 and 2", {d["checkpoint"] for d in decs} >= {"1", "2"}, sorted({d["checkpoint"] for d in decs}))
        a("Every DEC verbatim was typed by the user", decs and all(any(norm(d["verbatim"]) in t for t in typed) for d in decs),
          [d["verbatim"][:60] for d in decs if not any(norm(d["verbatim"]) in t for t in typed)])
        a("No provenance rejections", not [e for e in ev if e["event"] == "provenance_rejection"], [e["reason"] for e in ev if e["event"] == "provenance_rejection"])
        a("requirements-parser and gap-analyst invoked", {"requirements-parser", "gap-analyst"} <= set(subs), subs)
        lab = rs[0] / "status_labels.json"
        a("Labels derived with research routing", lab.exists() and json.loads(lab.read_text())["gap_routing"], "")
        a("Abort reason says stage 8 not built", "8" in (man.get("abort_reason") or "") and "not built" in (man.get("abort_reason") or ""), man.get("abort_reason"))
    if "eval-8" in name:
        a("Stages 1-10 completed (or 8-10 legitimately skipped)", all(st.get(k, {}).get("status") in ("completed", "skipped") for k in [str(i) for i in range(1, 11)]), {k: v["status"] for k, v in st.items()})
        reg = json.loads((rs[0] / "status_registry.json").read_text())["items"] if (rs[0] / "status_registry.json").exists() else {}
        fnd = {k: v for k, v in reg.items() if k.startswith("F-")}
        a("Findings registered and none left pending", fnd and all(v["verification"] != "pending" for v in fnd.values()), {k: v["verification"] for k, v in fnd.items()})
        a("At least one finding kept", any(v["verification"] == "kept" for v in fnd.values()), "")
        labels = json.loads((rs[0] / "status_labels.json").read_text())["gap_routing"]
        researched = {p.stem for p in (rs[0] / "findings").glob("*.json")} if (rs[0] / "findings").exists() else set()
        a("Research only on gaps approved for research", researched and researched <= {g for g, r in labels.items() if r["research_allowed"]}, (researched, labels))
        log = [json.loads(l) for l in (rs[0] / "fetch_log.jsonl").read_text().splitlines()] if (rs[0] / "fetch_log.jsonl").exists() else []
        a("Sources fetched via fetch_source.py in fixture mode", log and all(e["mode"] == "fixture" for e in log), len(log))
        a("Searches answered by H4 and counted by H3", any(e["event"] == "search_stub" for e in ev) and (rs[0] / "budget/searches.jsonl").exists(), "")
        a("researcher and source-verifier invoked", {"web-researcher", "source-verifier"} <= set(subs), subs)
        a("No provenance rejections", not [e for e in ev if e["event"] == "provenance_rejection"], "")
        a("Only budget blocks, if any", all(e["hook"] == "H3" for e in ev if e["event"] == "block"), [(e["hook"], e["reason"][:80]) for e in ev if e["event"] == "block"])
        a("Abort reason says stage 11 not built", "11" in (man.get("abort_reason") or "") and "not built" in (man.get("abort_reason") or ""), man.get("abort_reason"))
    if "eval-3" in name:
        a("No capture attempted", not (rs[0] / "capture").exists(), "")
        a("Report names blocked_address", "blocked_address" in final, final[:200])
    (d / "with_skill/grading.json").write_text(json.dumps({"expectations": A, "summary": {"passed": sum(x["passed"] for x in A), "failed": sum(not x["passed"] for x in A), "total": len(A), "pass_rate": round(sum(x["passed"] for x in A) / len(A), 2)}}, indent=2))
    (d / "with_skill/timing.json").write_text(json.dumps({"total_duration_seconds": m["duration_s"], "cost_usd": m["cost_usd"]}))
    print(d.name, f"{sum(x['passed'] for x in A)}/{len(A)}", [x["text"] for x in A if not x["passed"]])
