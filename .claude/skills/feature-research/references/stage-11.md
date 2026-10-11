# Stage 11: Feasibility and cross-cutting analysis

Goal: the cross-cutting items the specification must address, each with an honest basis:
required by the customer, supported by a kept finding, recommended for consideration, or
undecided. §9.9.

## Steps

1. `run_state.py verify`, `run_state.py stage 11 --run <run-id> --start`.
2. Agent tool, `subagent_type: feasibility-analyst`, prompt:

   ```
   Run ID: <run-id>
   Run directory: <absolute run dir>
   Supplied documents: <absolute paths of repository or technical documents the user supplied, or none>
   Write: <run dir>/feasibility.json (schema: feasibility).
   Warnings, if any: <run dir>/warnings/feasibility-analyst.json.
   ```

   Only pass documents the user explicitly supplied or pointed you to. Never describe the
   existing system to the agent yourself.
3. `validate.py feasibility <run dir>/feasibility.json`; one retry (new Agent call) with errors.
4. `status_rules.py register feasibility.json --run <run-id>`. It enforces the §9.9 mapping:
   `required_by_customer` must cite a live REQ, `supported_by_evidence` a kept finding;
   `undecided` items get an `unknown` issue. A refusal is a validation error: one retry.
5. `run_state.py stage 11 --run <run-id> --complete`.

## Report

Item counts by classification, new unknowns, assumptions, documents inspected, warnings.
