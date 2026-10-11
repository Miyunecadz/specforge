# Stage 6: Analyse gaps

Goal: missing features, states, broken flows, contradictions and unresolved roles or risks,
each routed to research or the customer. Performed by the `gap-analyst` subagent. §9.4.

## Steps

1. `run_state.py verify`, `run_state.py stage 6 --run <run-id> --start`.
2. Agent tool, `subagent_type: gap-analyst`, prompt:

   ```
   Run ID: <run-id>
   Run directory: <absolute run dir>
   Checklist path: <skill_dir>/checklists/gap-checklist.md
   Read: <run dir>/inventory.json, <run dir>/requirements.json, <run dir>/status_registry.json,
   <run dir>/decisions.json and the checklist.
   Write: <run dir>/gaps.json (schema: gaps). Set run_id to <run-id>.
   Warnings, if any: <run dir>/warnings/gap-analyst.json (schema: warnings).
   ```

3. `validate.py gaps <run dir>/gaps.json`; one retry with errors, then `stage 6 --fail`.
4. `status_rules.py register gaps.json --run <run-id>`.
5. `run_state.py stage 6 --run <run-id> --complete`.

## Report

Gap counts by priority and route, warnings. Then Stage 7.
