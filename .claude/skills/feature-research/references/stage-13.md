# Stage 13: Checkpoint 3, product decisions

Goal: the customer decides what research could not. Unanswered questions stay open and
drafting continues. §9.11, §7 Checkpoints.

## Present

1. `run_state.py verify`, `run_state.py stage 13 --run <run-id> --start`,
   `run_state.py await-user 3 --run <run-id>`.
2. First list the Checkpoint 2 decisions with your interpretation of each, so the user can
   correct a misreading.
3. Read `<run dir>/questions.json`. Present the questions in order:
   `Q-001 (critical, blocking): <question>`, why it matters, the options with their trade-offs,
   and the recommendation only if the file has one (say which finding supports it). Then list
   `implementation_details` briefly as "settled later unless you object".
4. Tell the user they can answer by question ID, choose an option, answer in their own words,
   or leave a question open; open questions stay listed as open in the specification.
5. End with the dedicated-session note and **end your turn**.

## Record

`run_state.py continue`, then `status_rules.py decide --run <run-id> --checkpoint 3
--answers-b64 <base64>`, same answer format and verbatim rules as Stage 5, with
`question_ids` set to the `Q-` ids answered. Actions here: `approve`, `reject`, `defer` on the
affected `FEA-`, `F-GAP-`, `REQ-`, `GAP-` or `ASM-` items; `clear_issue` (`unknown` or
`conflicting`) when the answer settles it; `create_requirement` when the answer states a new
requirement; `leave_open` for questions the user leaves open. Research-supported items are not
approved unless the user approves them.

Then `status_rules.py labels --run <run-id>` and `run_state.py stage 13 --run <run-id> --complete`.
If `labels` lists any `stale_approved` items, run Checkpoint 13R next (`stage-13r.md`);
otherwise go to Stage 14.

## Report

Decisions with interpretations, requirements created, items approved, rejected or deferred,
questions left open.
