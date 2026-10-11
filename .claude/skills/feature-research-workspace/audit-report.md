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

## Phase 1b re-audit (§21.1): feature-research APPROVED

Changed: Stage 2 row now "available (HTML, image, Figma)"; stage-02.md describes Figma capture (read-only
FIGMA_TOKEN never seen by the orchestrator, figma_max_frames, rate-limit retries, partial when frames are
skipped, recordings in fixture mode); build label Phase 1b. check_skill.py: 0 FAIL, 14 accepted WARNs
(library modules, agents-src). Checklist items all PASS; consistency checked against capture_mockup.py and
_lib/figma.py. Test prompts: Figma URL without a token → check_url auth_required, Stage 1 completes, run
aborted with setup instructions (stage-01.md step 4/7) PASS; Figma recording in fixture mode → stages 1–3
(e2e eval 6, 11/11) PASS; earlier prompts re-run in iteration 6, all PASS (57/57).
feature-research-subagent-rules: unchanged, no re-audit required.
