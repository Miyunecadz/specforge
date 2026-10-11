# Stage 13R: Re-confirmation checkpoint

Goal: the user re-confirms, supersedes or leaves open each approved item that became stale
because an input or decision it depended on changed after Checkpoint 3. §9.11a, §6 Stale flag.

Run it only when `status_rules.py labels` lists `stale_approved` items (`run_state.py` refuses
otherwise), before Stage 14, and again after Stage 15 if change-impact analysis made more
items stale (Phase 5).

## Present

1. `run_state.py verify`, `run_state.py stage 13R --run <run-id> --start`,
   `run_state.py await-user 13R --run <run-id>`.
2. For each stale item: what the user approved (the item and its content), the DEC that
   approved it (`decisions.json`), and what changed (the registry's `stale_reason`). Ask them to
   re-confirm it, supersede it, or leave it open.
3. Say that items left open stay labelled **Stale** in the specification and in Open
   Questions, and that the publication status can then be no better than
   `validated_with_warnings`.
4. Dedicated-session note; **end your turn**.

## Record

`run_state.py continue`, then `status_rules.py decide --run <run-id> --checkpoint 13R
--answers-b64 <base64>` (same format and verbatim rules). Actions: `reconfirm` (clears
`stale`), `supersede` (with `replacement_id` when the user names one), `leave_open`.
Then `status_rules.py labels --run <run-id>` and `run_state.py stage 13R --run <run-id> --complete`.

## Report

Items re-confirmed, superseded and left open (still Stale).
