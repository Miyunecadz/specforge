# Stage 12: Generate customer questions

Goal: at most `max_customer_questions` (config, default 10) plain-language questions for the
decisions research could not settle. §9.10.

## Steps

1. `run_state.py verify`, `run_state.py stage 12 --run <run-id> --start`.
2. `status_rules.py labels --run <run-id>` (so routing and stale items are current).
3. Agent tool, `subagent_type: question-generator`, prompt:

   ```
   Run ID: <run-id>
   Run directory: <absolute run dir>
   Maximum questions: <review.max_customer_questions from input/config.yaml>
   Write: <run dir>/questions.json (schema: questions).
   Warnings, if any: <run dir>/warnings/question-generator.json.
   ```

4. `validate.py questions <run dir>/questions.json`; one retry with errors.
5. `run_state.py stage 12 --run <run-id> --complete`. It checks the limit, ordering, ids,
   that affected ids exist, and that every recommendation names a listed option and cites only
   kept findings. Treat failures like validation errors (one retry).

## Report

Number of questions by priority (blocking), how many carry a recommendation, implementation
details folded, open decisions not asked.
