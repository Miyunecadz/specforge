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

## Phase 2 re-audit (§21.1): feature-research APPROVED

Changed: stages 4–7 available; `--resume` row; checkpoint protocol (clarify instead of deciding on
contradictory answers); retry is a new Agent call (SendMessage is blocked by H5); Example shows Checkpoint 1;
new references stage-04..07; stage-01 records prior decisions. check_skill.py: 0 FAIL, 17 accepted WARNs
(library modules and three agents-src files consumed by install_agents.py). Checklist all PASS; consistency
checked against status_rules.py (decide flags, actions), run_state.py (await-user/continue/resume),
stages.py (blocking questions, registration checks) and hooks (H1 provenance, H5 SendMessage).
Test prompts: `/feature-research <url> '<reqs>'` → Checkpoint 1 presented, turn ended (e2e eval 7) PASS;
user answers → DECs with exact verbatim, Checkpoint 2, abort at Stage 8 (eval 7, 14/14) PASS;
blocking question unanswered → re-asked, not bypassed (iterations 7–8) PASS; `--resume <id>` at an open
checkpoint → re-present with recorded rounds (resume row; unit tests) PASS.
feature-research-subagent-rules: unchanged.

## Phase 3 re-audit (§21.1): feature-research APPROVED

Changed: stages 8–10 available; references stage-08..10 (sequential research with set-gap, both researcher
variants, budgets enforced by H3 and fetch_source.py, citation check, semantic verification, stage skips);
build label Phase 3. check_skill.py: 0 FAIL; WARNs are library modules and agents-src files (accepted).
Consistency checked against fetch_source.py (command form, refusals), verify_citations.py (exit 1 is a result),
status_rules.py (register findings, verification --from), run_state.py (set-gap, --skip), H1 (exact fetch
form for web-researcher), H3/H4. Test prompts: research path (e2e eval 8, 16/16: 2 approved gaps researched,
4 searches stubbed by H4 and counted by H3, 3 fetches, 7/7 citations passed, 6 kept / 1 dropped) PASS;
no approved research gaps → stages 8–10 skipped (stage-08/09/10 skip rules; unit test) PASS; earlier prompts
unchanged in behaviour (evals 1–6 iteration 12). Eval 7 superseded by eval 8 (recorded in evals.json).
