# Stage 14: Write specification

Goal: the specification, in the template's sections and line format, with every statement
tagged with its source item and derived label. §9.12, §13.

## Steps

1. `run_state.py verify`; then `status_rules.py labels --run <run-id>`. If `stale_approved` is
   not empty and Checkpoint 13R has not run, run it first (`stage-13r.md`).
2. `run_state.py stage 14 --run <run-id> --start` (it refuses while approved items are stale and
   13R has not completed).
3. Agent tool, `subagent_type: doc-writer`, prompt:

   ```
   Mode: draft
   Run ID: <run-id>
   Run directory: <absolute run dir>
   Template path: <skill_dir>/templates/spec-template.md
   Write: <run dir>/spec.md
   Warnings, if any: <run dir>/warnings/doc-writer.json
   ```

4. **Before** any check: `status_rules.py register spec.md --run <run-id>` (registers the ASM-W
   block; new assumptions are always `not_reviewed`, label Assumption), then
   `status_rules.py labels --run <run-id>`.
5. `run_state.py stage 14 --run <run-id> --complete` (it keeps a copy of the draft in
   `history/`).

## Report

Line counts (FR, NFR, BR, AC, draft ACs), state tables, new assumptions, warnings.
