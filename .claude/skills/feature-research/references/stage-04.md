# Stage 4: Parse requirements

Goal: the customer's stated requirements, exact quotes, priorities, assumptions,
clarifying questions and conflicts. Performed by the `requirements-parser` subagent. §9.2.

## Steps

1. `run_state.py verify --run <run-id>`, then `run_state.py stage 4 --run <run-id> --start`.
2. Agent tool, `subagent_type: requirements-parser`, prompt:

   ```
   Run ID: <run-id>
   Run directory: <absolute run dir>
   Read: <run dir>/input/requirements.md (and <run dir>/decisions.json if it exists).
   Write: <run dir>/requirements.json (schema: requirements). Set run_id to <run-id>.
   Warnings, if any: <run dir>/warnings/requirements-parser.json (schema: warnings).
   ```

3. `validate.py requirements <run dir>/requirements.json` (and `validate.py warnings …` if the
   warnings file exists). On failure: one retry with the exact errors, then
   `stage 4 --fail` and stop.
4. Register: `<python> <skill_dir>/scripts/status_rules.py register requirements.json --run <run-id>`.
   It rejects duplicate ids and applies the proposed status changes and conflicts.
5. `run_state.py stage 4 --run <run-id> --complete`. It also checks every `source_quote` is
   an exact quote from `input/requirements.md` and that this version was registered. If a
   quote check fails, give the parser the errors once (then re-register before completing).

## Report

Counts by priority, number of clarifying questions (blocking), assumptions, conflicts,
warnings. Then go straight to Stage 5.
