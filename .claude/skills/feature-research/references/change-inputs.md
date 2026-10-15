# Changed requirements (change-impact analysis)

Use when the customer's requirements change while a run is open, after Stage 4. §15.

1. `run_state.py verify --run <run-id>`. No stage may be running; if one is (for example an open checkpoint),
   complete it first.
2. Record the new version and find what it affects:

   ```
   <python> <skill_dir>/scripts/run_state.py change-inputs --run <run-id> --requirements-file '<path>' --reason '<reason>'
   ```

   If it refuses (exit 3), report its reason and stop; nothing was changed. Before Stage 4
   completes, the user starts a new run with the new requirements instead.

   It saves `input/requirements-v<n>.md` (the original stays), compares each requirement's
   source quote with the new text, and writes `input/change-<n>.json` listing the changed
   REQs, the added text, and every dependent item (gaps, their findings, feasibility items,
   assumptions) with a stale reason.
3. Apply the stale reasons: `status_rules.py apply input/change-<n>.json --run <run-id>`.
   Approved items stay approved and become **Stale**; unapproved ones become superseded.
   Nothing is un-approved.
4. `status_rules.py labels --run <run-id>`.
5. Report the impact: changed REQs, the added text (quoted), items marked stale, items
   superseded.
6. Continue:
   - Checkpoint 3 already passed: if `labels` lists `stale_approved` items, run Stage 13R
     (`stage-13r.md`) next. If Stage 15 had completed, completing 13R marks Stages 14–16 stale
     once per run (`stage-15.md` step 6); re-run them. Otherwise continue from the first stage
     not yet completed. If `stage --start` refuses a stage as already completed, or 13R as
     already run after review, do not work around it: report that the specification was not
     rewritten for this change and that the remaining items stay Stale.
   - Checkpoint 3 not passed yet: continue the stage loop. At Checkpoint 2, list the stale
     items and their `stale_reason` before the gap table; at Checkpoint 3 the
     question-generator includes stale approved items; any still stale before Stage 14 go
     to Checkpoint 13R.
   - New requirements in the added text become requirements only through a checkpoint
     answer (`create_requirement`); never add them yourself.
