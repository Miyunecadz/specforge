# Stage 16: Report

Goal: an honest summary, the publication status written into the specification, and the
run closed. §7 Stage 16, §9.14.

## Steps

1. `run_state.py verify`, `run_state.py stage 16 --run <run-id> --start`.
2. `run_state.py report --run <run-id>`: merges agent warnings into `warnings.json`, computes the
   publication status (`validated`, `validated_with_warnings`, `not_fully_validated`, `blocked`;
   always `eval_only` in fixture mode) and writes `run_summary.json`.
3. Agent tool, `subagent_type: doc-writer`, `Mode: final`, same run details plus
   `Run summary: <run dir>/run_summary.json`. It rewrites only Document Status.
4. `<python> <skill_dir>/scripts/check_spec.py --run <run-id> --final` (Document Status shows the
   computed status exactly; nothing else changed). If it fails, one more `final` pass, then
   re-check.
5. `run_state.py record-revision --run <run-id> --final`, then
   `run_state.py stage 16 --run <run-id> --complete`, then `run_state.py end --run <run-id>`
   (removes `.active_run`; the session is released).

## Report to the user (in chat)

From `run_summary.json` and the artifacts:

- run ID and the spec path (`<run dir>/spec.md`); publication status and its reasons; run mode;
- counts: requirements by label, gaps by approval, findings by verification, questions answered
  vs open, stale items;
- capture and research limitations; budget usage (searches, fetches per gap);
- hook blocks, tamper reports, decision-provenance rejections;
- unresolved review issues; outstanding decisions (open questions), with your recorded
  interpretation of each decision;
- in fixture mode, that the status is `eval_only` and what the checks would have given.

The publication status describes workflow validation, not a guarantee that the product is
correct or compliant: say so.
