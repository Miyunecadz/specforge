# Stage 7: Checkpoint 2, approve gaps and routing

Goal: the user decides which gaps matter and how each is resolved. Approving research on a
gap is not approval of any solution. §9.5, §7 Checkpoints.

## Present

1. `run_state.py verify`, `run_state.py stage 7 --run <run-id> --start`,
   `run_state.py await-user 2 --run <run-id>`.
2. First, list the decisions recorded at Checkpoint 1 with your interpretation of each
   (from `decisions.json`), so the user can catch a misreading.
3. Read `<run dir>/gaps.json` and present:

   | ID | Gap | Reason | Priority | Path | Why it matters | Research objective |
   |---|---|---|---|---|---|---|

   (Research objective: the research questions, or "customer decision".)
4. Tell the user they may approve, reject, defer, reprioritise, add gaps, change a route, or
   edit research objectives, by gap ID. Only approved gaps routed to research or both are
   researched; rejected and deferred gaps are kept and reported.
5. End with the dedicated-session note and **end your turn**.

## Record

`run_state.py continue`, then `status_rules.py decide --run <run-id> --checkpoint 2
--answers-b64 <base64>`, same answer format and verbatim rules as Stage 5. Actions here:
`approve`, `reject`, `defer`, `reopen`, `set_priority` (`critical|important|optional`),
`set_resolution_path` (`research|customer|both`), `set_research_questions` (1–3 questions),
`create_gap` (`title`, `description`, `resolution_path`, `priority`, `research_questions`
when routed to research). Never approve a gap the user did not address.

Then `status_rules.py labels --run <run-id>` (it lists `research_allowed` gaps) and
`run_state.py stage 7 --run <run-id> --complete`.

## Report

Approved, rejected, deferred and added gaps; the gaps that will be researched (from
`labels`); decisions with interpretations.
