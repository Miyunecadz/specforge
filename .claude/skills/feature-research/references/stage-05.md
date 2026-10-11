# Stage 5: Checkpoint 1, confirm requirements

Goal: the user confirms, corrects or rejects the parsed requirements and answers the
clarifying questions. Their answers become decisions only through `status_rules.py decide`.
§9.3, §7 Checkpoints.

## Present

1. `run_state.py verify`, `run_state.py stage 5 --run <run-id> --start`, then
   `run_state.py await-user 1 --run <run-id>`.
2. Read `<run dir>/requirements.json`. Present, concisely and grouped by topic:
   - **Requirements**: table `| ID | Requirement (customer's words) | Priority | Type |`.
   - **Conflicts**: both sides, unreconciled.
   - **Assumptions**: `ASM-P-…` with what must be confirmed.
   - **Questions**: `CQ-…`, blocking ones marked **(blocking)**, each with why it matters.
   - **Prior decisions** recorded at intake, if any.
3. Ask the user to answer by ID (for example "CQ-001: …", "REQ-003: reject", "all others
   approved"), and say that non-blocking questions may be left open but blocking ones cannot.
4. End with the dedicated-session note from SKILL.md and **end your turn**.

## Record

When the user replies: `run_state.py continue --run <run-id>`, then build the answers and run
`status_rules.py decide --run <run-id> --checkpoint 1 --answers-b64 <base64>`.

Answers JSON (UTF-8, then standard base64):

```json
{"schema_version": 1, "checkpoint": "1", "source": "user", "answers": [
  {"verbatim": "<the user's exact words for this answer, copied character for character>",
   "interpretation": "<what you understood, in one sentence>",
   "presented": "<the question or item it answers>",
   "question_ids": ["CQ-001"], "affected_ids": ["REQ-001", "CQ-001"],
   "actions": [{"type": "create_requirement", "statement": "...", "req_type": "functional", "priority": "must"},
               {"type": "clear_issue", "item_id": "REQ-001", "issue": "unknown"},
               {"type": "approve", "item_id": "REQ-001"}]}
]}
```

- One answer per distinct thing the user said. `verbatim` must be an exact substring of the
  user's message (hook H1 checks this against the transcript): do not fix typos, merge
  sentences or paraphrase. A blanket answer ("everything else is fine") is one answer whose
  actions approve each remaining REQ.
- Actions: `approve`, `reject`, `defer`, `reopen` (rejected item), `clear_issue` (with
  `issue`), `create_requirement` (when the answer establishes a requirement: new REQ, labelled
  Decided), `leave_open` (user chose not to answer a non-blocking question). Use only what the
  user said; never approve something they did not address.
- If H1 blocks the command, show the user what was rejected and ask them to answer again.
- If `decide` returns an error (invalid transition, unknown id), fix the JSON to match what
  the user actually said; if their answer cannot be expressed, ask them.

Then `status_rules.py labels --run <run-id>` and `run_state.py stage 5 --run <run-id> --complete`.
If it reports an unanswered **blocking** question, run `run_state.py await-user 1` again, ask
only that question, and end your turn. Never bypass it.

## Report

Decisions recorded (DEC ids with your interpretation of each), requirements created,
approved, rejected, deferred, still open. The interpretations are shown again at the next
checkpoint.
