# Stage 10: Semantic verification

Goal: an independent judgement, against the saved source text, of whether each finding that
passed the citation check is actually supported. §9.8.

## Steps

1. `run_state.py verify`, `run_state.py stage 10 --run <run-id> --start`. If no finding is
   pending (none passed Stage 9, or research was skipped), run
   `run_state.py stage 10 --run <run-id> --skip --reason 'no findings to verify'` and stop
   (Stage 11 is not built yet).
2. Agent tool, `subagent_type: source-verifier`, prompt:

   ```
   Run ID: <run-id>
   Run directory: <absolute run dir>
   Read: <run dir>/citation_check.json, the findings in <run dir>/findings/, the sources in
   <run dir>/sources/, <run dir>/gaps.json, <run dir>/decisions.json and <run dir>/status_labels.json.
   Write: <run dir>/verified_findings.json (schema: verified_findings).
   Warnings, if any: <run dir>/warnings/source-verifier.json.
   ```

3. `validate.py verified_findings <run dir>/verified_findings.json`; one retry with errors.
4. `status_rules.py verification --run <run-id> --from semantic`. It refuses if a finding that
   passed the citation check was not reviewed, or a citation-failed finding was kept.
5. `status_rules.py labels --run <run-id>`, then `run_state.py stage 10 --run <run-id> --complete`.

## Report

Kept and dropped findings (with reasons), contradictions, and what research could not answer.
Research-supported findings are not approved requirements; they are presented for decision
later.
