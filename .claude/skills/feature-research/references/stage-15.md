# Stage 15: Review and validate

Goal: the specification checked mechanically and reviewed independently, with at most two
revision rounds. Failed checks stay failed. §9.13, §7 Stage 15.

## Steps

1. `run_state.py verify`, `run_state.py stage 15 --run <run-id> --start`. Round = 1.
2. `<python> <skill_dir>/scripts/check_spec.py --run <run-id> --round <round>` (exit 1 means
   blocking [code] failures; a result, not an error).
3. Agent tool, `subagent_type: doc-reviewer`, prompt:

   ```
   Run ID: <run-id>
   Run directory: <absolute run dir>
   Round: <round>
   Write: <run dir>/review.json (schema: review).
   Warnings, if any: <run dir>/warnings/doc-reviewer.json.
   ```

   `validate.py review <run dir>/review.json`; one retry with errors.
4. If `validation.json` has `blocking_failures` or `review.json` has `passed: false`, and fewer
   than `review.revision_rounds` (config, 2) revisions were made:
   1. Agent tool, `subagent_type: doc-writer`, `Mode: revise`, same run details, fix list:
      "apply every failing item in <run dir>/validation.json and every fix in <run dir>/review.json".
   2. `run_state.py record-revision --run <run-id>` (records the new spec version; refuses if
      the spec changed without a doc-writer invocation).
   3. `status_rules.py register spec.md --run <run-id>` and `status_rules.py labels --run <run-id>`
      (new ASM-W items first).
   4. Round += 1; repeat from step 2.
5. `run_state.py stage 15 --run <run-id> --complete`. It refuses while blocking checks fail and
   revision rounds remain. When both rounds are used and failures remain, it completes: the
   publication status will be `not_fully_validated` and the failures are listed. Never weaken a
   check, edit `validation.json` or `review.json`, or describe a failed review as passed.
6. Unless the post-review Checkpoint 13R already ran in this run: if change-impact analysis
   has made approved items stale after Stage 13 (including a
   `change_after_checkpoint_3` in a `--non-interactive` run)
   (`status_rules.py labels` → `stale_approved`), run Checkpoint 13R now (allowed once after
   review); it marks Stages 14–16 for one re-run, which you then perform (Stages 14 and 15
   again). Items going stale after that stay Stale.

## Report

Per round: [code] failures, reviewer blocking failures and warnings, fixes applied; final
state of both checks.
