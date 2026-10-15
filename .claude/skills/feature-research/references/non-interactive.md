# Non-interactive eval runs

Only `run_evals.py` uses this, by launching `claude -p` with eval fixture mode set in the
process environment. Nobody is reading the session, so you never end your turn to wait for
an answer: every checkpoint answer comes from the case file through `status_rules.py decide
--from-case`, which matches the pre-written answers to the generated questions itself. You
never write, choose, or encode eval answers yourself. §16 Non-interactive mode.

## Start

1. Read the case file (`evals/cases/<case>/input.json`). Take `mockup`, `requirements_file`
   and, if present, `prior_decisions_file`. Do not read `expected.json` or anything else in
   the case directory: it is the answer key for grading.
2. Follow `stage-01.md` with:

   ```
   <python> <skill_dir>/scripts/run_state.py start --mockup-url '<mockup>' --requirements-file '<requirements_file>' --non-interactive '<case file>'
   ```

   adding `--prior-decisions '<prior_decisions_file>'` when the case has one. A refusal
   (fixture mode not active, case file outside `evals/cases/`) ends the run: report it and stop.

## Checkpoints

At Checkpoints 1, 2, 3 and 13R (Stages 5, 7, 13 and 13R), replace the checkpoint protocol's "present and end your turn" with these three commands, in
this order, in the same turn:

```
<python> <skill_dir>/scripts/run_state.py await-user <checkpoint> --run <run-id>
<python> <skill_dir>/scripts/run_state.py continue --run <run-id>
<python> <skill_dir>/scripts/status_rules.py decide --run <run-id> --checkpoint <checkpoint> --from-case
```

Then do the rest of the stage's Record steps (labels, register, `stage --complete`) as its
reference says. In your stage report, list the `unmatched` entries `decide` printed:
questions left open and pre-written answers that matched nothing. Never try to answer them.
If `stage 5 --complete` refuses because a blocking question has no recorded answer, the case
file does not cover it: that is an eval result, not something to fix. If `decide --from-case`
or `stage --complete` refuses, report the reason and stop the run with
`run_state.py stage <stage> --run <run-id> --fail --reason '<reason>'`.

## Changed requirements after Checkpoint 3

If the case file has `change_after_checkpoint_3`, then after Stage 15 completes, follow
`change-inputs.md` with that object's `requirements_file` and `reason`, then `stage-15.md`
step 6 (post-review Checkpoint 13R, then re-run Stages 14 and 15) before Stage 16.

## Ending

Run Stages 14–16 as usual. The publication status is always `eval_only`. Finish with the
Stage 16 report; do not wait for anything after it.
