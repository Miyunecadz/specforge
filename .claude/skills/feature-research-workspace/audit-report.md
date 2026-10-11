# Skill-auditor results (§21.1, §21.2), Phase 1a

Intent source: BUILD_SPEC.md §3, §7, §8 and the Phase 1a plan, approved by the user on 2026-10-11.

## feature-research: round 1 NEEDS CHANGES, round 2 APPROVED (Review mode)

Round 1 fixes (user approved "apply all"): add a "Use when" clause; replace `references/stage-NN.md`
with a real file name; Stage 1 skips steps 1 and 2 (no run to verify before start); remove `<>` from
the description; add an Example section; delete `__pycache__`. Diff base: `audit-original/`.

Round 2 checklist: Intent match PASS (stage loop, checkpoint protocol, hard rules, vocabulary
precedence, clean stop at unbuilt stages); Frontmatter PASS; Triggering PASS (disable-model-invocation:
true; "Never start it from an ordinary request"); Scope PASS (neighbour overlap at most 0.05); Instructions PASS;
Edge cases PASS (missing arguments, refusals, tamper, unbuilt stages, failed capture); Examples PASS;
Consistency PASS; File structure PASS; Length PASS (208 lines).
Accepted WARNs: 13 `scripts/_lib/*` modules and `agents-src/mockup-extractor.md` are "unreferenced" by
SKILL.md but are imported by the scripts and consumed by install_agents.py.

Test prompts: (1) `/feature-research <url> '<reqs>'` → Stage 1 per stage-01.md, PASS (e2e eval 1);
(2) near miss "write a spec from this figma link" → not loadable (disable-model-invocation, probe a), PASS;
(3) missing requirements → asks, no run, PASS (e2e eval 4); (4) `--resume <id>` → "Phase 2" and stop, PASS.

## feature-research-subagent-rules: round 1 NEEDS CHANGES, round 2 APPROVED

Round 1 fix: "Use only inside those subagents" → "Use when running as one of those subagents";
heading renamed "Warnings file format (example)". Round 2: 0 FAIL, 0 WARN; every checklist item PASS.
Test prompts: an ordinary-session question about subagent rules cannot load the skill (both flags,
probe a/b) PASS; embedded copy present verbatim in the generated agent (drift test) PASS.
