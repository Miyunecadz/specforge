# Stage 8: Research

Goal: checkable evidence for each gap the user approved for research, gathered within
budget and fetched only through `fetch_source.py`. §9.6, §11.4.

## Steps

1. `run_state.py verify`, `run_state.py stage 8 --run <run-id> --start`.
2. Read `<run dir>/status_labels.json`. The gaps to research are those with
   `gap_routing.<gap>.research_allowed: true`. If there are none, run
   `run_state.py stage 8 --run <run-id> --skip --reason 'no gaps approved for research'`
   and go to Stage 9 (which you will also skip).
3. Research the gaps **one at a time** (search budgets are attributed to the active gap). For
   each gap, in priority order:
   1. `<python> <skill_dir>/scripts/run_state.py set-gap <GAP-id> --run <run-id>`. Its output
      gives the budget (`searches_per_gap`, `fetches_per_gap`, `findings_per_gap`).
   2. If `researcher_variant` (setup file) is `web-researcher`: Agent tool,
      `subagent_type: web-researcher`, prompt:

      ```
      Run ID: <run-id>
      Run directory: <absolute run dir>
      Gap ID: <GAP-id>
      Research questions: <from status_labels.json gap_routing>
      Related: <related REQ and SCR ids from the gap>
      Budget: searches <n>, fetches <n>, findings <n>
      Fetch command: <python> <skill_dir>/scripts/fetch_source.py --run <run-id> --gap <GAP-id> '<url>'
      Write: <run dir>/findings/<GAP-id>.json (schema: findings).
      Warnings, if any: <run dir>/warnings/web-researcher.json.
      ```

      If it is `web-researcher-fallback`: run the agent with `Pass: 1` (same details, writing
      `fetch_requests/<GAP-id>.json`); then run `fetch_source.py` yourself for each requested
      URL, at most the fetch budget, one Bash call each; then run the agent again with
      `Pass: 2` and the list of fetch results (URL → outcome, source_id, source_type,
      publication_date).
   3. `validate.py findings <run dir>/findings/<GAP-id>.json`; one retry (new Agent call) with
      the errors.
   4. `status_rules.py register findings/<GAP-id>.json --run <run-id>`.
4. `run_state.py set-gap --clear --run <run-id>`, then
   `run_state.py stage 8 --run <run-id> --complete`. It refuses if an approved gap has no
   findings file, a findings file exists for an unapproved gap, or a file is unregistered.

Searches beyond budget are blocked by hook H3 and fetches beyond budget are refused by
`fetch_source.py`; that is expected, not an error. Never search or fetch yourself.

## Report

Per gap: findings (recommendations), searches and fetches used against budget, sources
unavailable or refused, unanswered questions, warnings.
