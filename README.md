# Feature Research Agent

A Claude Code workflow that turns a product mockup URL and a customer's requirements into a
traceable, evidence-backed feature specification, without inventing requirements or
silently making product decisions.

- Specification: [`docs/feature-research-agent/BUILD_SPEC.md`](docs/feature-research-agent/BUILD_SPEC.md)
- Plan and recorded decisions: [`docs/feature-research-agent/PLAN.md`](docs/feature-research-agent/PLAN.md)

> **Build status: Phase 2.** Stages 1–7 work: intake (with prior decisions), mockup capture
> (HTML, images, Figma), inventory extraction, requirements parsing, Checkpoint 1, gap
> analysis and Checkpoint 2, with the status registry, decision provenance, `--resume` and
> `--abort`. When a run reaches Stage 8 the orchestrator aborts it with the reason "stages
> 8–16 are not built yet", so the session is released. Research and
> citation checks (Phase 3), feasibility and decisions (Phase 4), spec writing and review
> (Phase 5), and the evaluation runner (Phase 6) come later. This README describes only what
> exists now.

## How it works

```
/feature-research <mockup-url> <requirements>        (you type it; it never starts on its own)
  │
  ▼  orchestrator skill (.claude/skills/feature-research/SKILL.md)
  │    Bash: only <python> <skill>/scripts/<name>.py …    (hook H1)
  │    Write/Edit: nothing during a run                    (hook H2)
  │    Skill, WebFetch, MCP tools, non-workflow agents: blocked during a run (hook H5)
  │
  ├─ Stage 1  run_state.py start, check_url.py   → input/, run_manifest.json
  ├─ Stage 2  capture_mockup.py                   → capture/
  ├─ Stage 3  mockup-extractor subagent           → inventory.json
  ├─ Stage 4  requirements-parser subagent        → requirements.json (registered)
  ├─ Stage 5  Checkpoint 1 (you answer)           → decisions.json via status_rules.py decide
  ├─ Stage 6  gap-analyst subagent                → gaps.json (registered)
  └─ Stage 7  Checkpoint 2 (you answer)           → decisions.json, status_labels.json
```

- **Scripts** do everything deterministic: run state, URL validation, capture, schema
  validation, hashing.
- **Subagents** do reasoning and extraction. They are generated into `.claude/agents/` by
  `install_agents.py` and have only the tools they need (mockup-extractor: Read, Write).
- **Hooks** enforce what prompts cannot (see "Hooks").
- **JSON Schemas** in `.claude/skills/feature-research/schemas/` define every artifact.

The orchestrator is a skill with `disable-model-invocation: true`: a request such as "write
a spec from this mockup" never starts it. Only typing `/feature-research` does.

## Prerequisites and setup

- Claude Code 2.1.296 or later (the capability checks in PLAN.md were run on 2.1.296).
- [`uv`](https://docs.astral.sh/uv/) and Python 3.12+.
- Linux or WSL on a filesystem with reliable `O_EXCL` lock files and atomic rename. This
  checkout lives on the WSL ext4 disk (`/mnt/e` here is not a Windows drive), which passed a
  1600-append lock test. A Windows drive mounted under `/mnt/<letter>` through drvfs may
  not be safe.

```bash
uv sync                                                  # creates .venv from uv.lock
.venv/bin/playwright install chromium                    # browser for HTML capture
sudo .venv/bin/playwright install-deps chromium          # system libraries (needs sudo)
.venv/bin/python .claude/skills/feature-research/scripts/install_agents.py
```

### Figma token

Figma capture needs a personal access token with **File content: Read-only** scope and no
write scopes (Figma → Settings → Security → Personal access tokens). Keep it outside the
repository and export it as `FIGMA_TOKEN` in the shell that starts Claude Code:

```bash
mkdir -p ~/.config/figma && chmod 700 ~/.config/figma
printf '%s' 'YOUR_TOKEN' > ~/.config/figma/token && chmod 600 ~/.config/figma/token
echo 'export FIGMA_TOKEN="$(cat ~/.config/figma/token)"' >> ~/.bashrc
```

Never paste it into a chat or a repository file. The workflow sends it only to
`api.figma.com` (never to the image hosts Figma links to), only on GET requests, and never
writes it to run files or logs. Without it, Stage 1 reports `auth_required` with these
instructions and the run stops.

Dependencies are pinned in `uv.lock` (`requirements.txt` is exported from it): `httpx`,
`trafilatura`, `playwright`, `jsonschema`, `PyYAML`, and `pytest` for development.

### install_agents.py

- Generates `.claude/agents/*.md` from `.claude/skills/feature-research/agents-src/`,
  embedding the shared subagent rules
  (`.claude/skills/feature-research-subagent-rules/SKILL.md`) verbatim in each agent.
  Preloading is not used: on this Claude Code version a skill marked
  `disable-model-invocation: true` is not delivered through `skills:` preloading.
- Installs exactly one researcher variant (`web-researcher` in identified mode, the default;
  its source arrives in Phase 3).
- Picks the interpreter: the project `.venv/bin/python` if present, otherwise `python3` or
  `python` from `PATH`, as an absolute path. It records that path, the hook mode and the
  installed agents in `.claude/feature-research.local.json` (gitignored, machine-specific).
- Refuses to run while a run is active, and hook H1 blocks it during a run.

**Never hand-edit `.claude/agents/`.** Edit `agents-src/` and re-run the installer. A test
fails if an installed agent differs from what its source and the shared rules generate.

## Usage

```
/feature-research https://proto.example.com/packages 'Package managers award a supplier package to one supplier.'
/feature-research https://proto.example.com/packages docs/customer-requirements.md
/feature-research --abort <run-id>
```

Requirements can be text or a path to a file. Text is passed to `run_state.py` as
base64, and the orchestrator compares the preserved copy with what you typed. If they differ
(possible with very long text), it aborts and asks you for a file instead.

`/feature-research --resume <run-id>` takes over a run that is waiting at a checkpoint, or
whose owning session has been silent for `active_run_timeout_minutes`; otherwise another
session may still be working on it and you must `--abort` first. Resume re-verifies every
hash, re-validates completed outputs against the current schemas (invalid ones make their
stage and later stages stale), binds the run to your session, and re-presents an open
checkpoint with the answers already recorded. Continuing the same conversation
(`claude --resume`) keeps the same session ID, so no resume is needed then.

`--non-interactive` exists only for evals and is
refused unless eval fixture mode is active (see "Eval fixture mode").

**A session is dedicated to its run** until the run ends or is aborted. During the run,
Bash in that session can run only the workflow's scripts. Other Claude Code sessions in
this repository are not affected. `/feature-research --abort <run-id>` works from any session.

## Checkpoints, decisions and status

At Checkpoints 1 and 2 the orchestrator presents what it needs, runs
`run_state.py await-user <N>`, and **ends its turn**. It never answers its own checkpoint.
When you reply, it runs `run_state.py continue` and then
`status_rules.py decide --checkpoint <N> --answers-b64 <base64>`. Each of your answers
becomes a `DEC-nnn` in `decisions.json`: your verbatim words, the orchestrator's
interpretation (shown back to you at the next checkpoint), the affected items and the
actions taken (approve, reject, defer, reopen, clear an issue, create a requirement or gap,
change a gap's priority, route or research questions). Blocking clarifying questions cannot
be bypassed: Stage 5 will not complete until each has an answer.

**Decision provenance.** Before `decide` runs, hook H1 reads the session transcript, finds
the `await-user <N>` call, and checks that every verbatim answer appears in a message you
**typed** after it. Tool results, hook-injected context (for example a style hook's
`additionalContext`), system reminders, skill expansions and command output never count,
so text from a fetched page or a mockup cannot become a decision. If the check fails the
command is blocked and you are asked to answer again. It fails closed if the transcript
cannot be read.

**Status registry.** `status_registry.json` (written only by `status_rules.py`) holds each
tracked item's approval, issues, decisions, staleness and (for findings) verification;
content artifacts never contain these fields. Every change is appended to the hash-chained
`status_history.jsonl`. Transitions follow BUILD_SPEC §6 exactly: nothing defaults to
approved except items created by your decisions, approval needs a decision, rejected items
need an explicit reopen, superseded is terminal, and approved items that become stale stay
approved and are re-confirmed by you. `status_rules.py labels` derives each item's display
label (Explicit, Decided: DEC-…, Approved: DEC-…, Inferred, Assumption, Stale: re-confirm,
Rejected, Deferred, …), its placement, and which approved gaps may be researched, into
`status_labels.json`.

## Run directory

Normal runs live in `runs/`; fixture-mode runs live in `evals/runs/`. Both are gitignored
because they may contain customer material.

```
runs/
  .active_run           the active run: id, mode, owning session, start time (run_state.py)
  .heartbeat            last guarded call per session + hook attestation (hooks)
  .hook_events.jsonl    blocks and subagent starts, hash-chained (hooks)
  <run-id>/
    run_manifest.json   stages, outputs and hashes, status (run_state.py)
    log.jsonl           audit log, hash-chained (run_state.py)
    input/              request.json, requirements.md, config.yaml, prior_decisions.json
    capture/            manifest.json, pages/, frames/, screenshots/, assets/ (capture_mockup.py)
    inventory.json      mockup-extractor
    requirements.json   requirements-parser
    gaps.json           gap-analyst
    checkpoints/        checkpoint-<N>-answers.json, every decide round (status_rules.py)
    decisions.json      DECs (status_rules.py)
    status_registry.json, status_history.jsonl, status_labels.json   (status_rules.py)
    warnings/<agent>.json
    integrity/<script>.json   hashes of continuously updated files
```

### File ownership, concurrent writes, tamper detection

Every file has exactly one writer (BUILD_SPEC §5). The machine-readable table is
`scripts/_lib/ownership.py`, and both hook H2 and tamper reports use it.

- Appends and replacements use `O_CREAT|O_EXCL` lock files with stale-lock detection
  (never `fcntl`/`flock`). Whole files are replaced through a temp file and `os.replace`.
- `run_state.py verify` runs before every stage. It re-hashes completed stage outputs,
  checks the manifest against the hash recorded in the log, checks `.active_run`, checks
  every hash-chained JSONL file, and reports any file that is not in the ownership table. A
  mismatch stops the run with a report naming the file, its owner and its last writer.
- `stage <N> --complete` refuses an agent stage unless the hooks recorded that agent's
  invocation after the stage started.

Limit: the hashes detect accidental or naive changes. Someone with shell access outside a
guarded session could rewrite a file and its recorded hash together.

## Hooks

Registered in `.claude/settings.json`. They run under the system `python3` (stdlib only).
A single PreToolUse dispatcher (`.claude/hooks/guard.py`) runs H5 → H1 → H2 in that order,
because separately registered hooks run in parallel.

| Hook | What it does during a run (owning session only) |
|---|---|
| **H1** Bash guard | Every Bash call must be exactly `<python> <skill>/scripts/<name>.py <args>`, using the recorded interpreter. It blocks env-variable prefixes, chaining, pipes, redirection, subshells, `$(...)`, backticks, globs and `~`. Arguments may be single-quoted (any characters except `'`) or double-quoted (no `$`, `` ` ``, `\`, `!`). Subagents get no Bash, except `web-researcher`, which may run only the exact `fetch_source.py` form (Phase 3). `status_rules.py decide` runs only after the decision-provenance check passes. |
| **H2** Write guard | Blocks Write/Edit everywhere outside the active run directory. Blocks script- and hook-owned files for everyone, and blocks all orchestrator writes in the run directory. Each subagent may write only the files it owns. Symlinks and relative paths are resolved first. |
| **H5** Tool guard | Blocks Skill, WebFetch and every `mcp__*` tool. WebSearch is allowed only for the installed researcher. The Agent tool is allowed only for the nine workflow agents. Any other tool not on the run allow-list (for example Monitor, Workflow, CronCreate, AskUserQuestion) is also blocked. |
| Recorder | SubagentStart: records each subagent invocation in `.hook_events.jsonl`. |
| H3, H4 | Search budget and eval search stub, Phase 3. |

The active run is bound to the Claude Code session that started it: hooks compare the
payload `session_id` with `.active_run`. With no active run, or in another session, the
hooks allow everything. If the payload ever lacked a session ID, every session would be
restricted until the heartbeat expires (`active_run_timeout_minutes`).

**Fail closed.** Claude Code treats a hook that exits with any non-zero code other than 2
as a non-blocking error. The dispatcher therefore catches every internal error and blocks
(exit 2) whenever a run is active. `run_state.py start` also requires a fresh **hook
attestation**: H1 records a digest of the exact `start` command, from the same session, in
`.heartbeat`. Without it, the run does not start, which proves the hooks are loaded.

## Security

- **URLs (§11.1).** `check_url.py`, `capture_mockup.py` and every browser request accept
  only http/https, with no credentials in URLs. Hostnames are resolved, and a URL is
  rejected if any address is loopback, private, link-local, CGNAT, reserved, multicast,
  documentation or cloud metadata (including IPv4-mapped, 6to4, Teredo and NAT64 forms).
  Redirects are re-validated. Connections go to the validated IP, with the hostname as Host
  and TLS SNI (DNS-rebinding mitigation). Redirect, timeout, byte and content-type limits
  apply. Anything that cannot be validated is rejected.
- **Capture.** Every browser request (subresources, iframes, popups, redirects) is
  intercepted at the browser-context level, fetched by the script through the same checks,
  and returned with `route.fulfill`, so Chromium never connects anywhere itself. Only
  GET/HEAD is served. WebSockets and service workers are blocked. Forms are never
  submitted. Links that look state-changing (logout, delete, …) are not followed. Blocked
  and failed requests are recorded, and the capture is then labelled **partial**.
- **Figma.** GET-only calls to the REST API with the read-only token. On HTTP 429 it waits
  for `Retry-After` (or exponential back-off from `figma_backoff_base_s`) and retries up to
  `figma_max_retries` times; waits over 120 s or exhausted retries are a capture failure.
  At most `figma_max_frames` frames are captured (only the linked node with `?node-id=`), and
  skipped frames make the capture **partial**. Frame images Figma links to go through the
  same SSRF checks; a blocked image is recorded and makes the capture partial.
- **Prompt injection.** All captured content is untrusted data. The shared subagent rules
  require agents to ignore embedded instructions and record them as
  `prompt_injection_attempt` warnings. The hooks limit what any injected instruction could
  do anyway.
- **Secrets.** Never written to run files. Query strings are redacted from recorded URLs.

### Residual risks

1. Outside a run (before `start`, after `end`), sessions have their normal permissions.
2. Decision provenance reads the Claude Code transcript, whose format is internal; it fails
   closed (blocks `decide`) if the format changes. It verifies your words, not the
   orchestrator's interpretation of them, which is shown back to you instead.
3. If `python3` is missing, hook commands fail with a non-2 exit, which Claude Code treats
   as non-blocking. The start-time attestation prevents new runs in that state.
4. DNS rebinding is mitigated for script fetches (pinned IP). Browser requests are fetched
   by the script, so the same protection applies to them.

## Configuration

`.claude/skills/feature-research/config.yaml` is validated against `config.schema.json`.
Every object is closed and every limit has a hard maximum, so configuration cannot disable
safety controls, enable fixture mode or `--non-interactive`, set the interpreter, or exceed
the eval budget caps ($10 per case, $60 per run).

Safe to change: capture limits (`max_pages`, `max_depth`, `figma_max_frames`, timeouts,
byte limits, `image_content_types`), `network.blocked_hostnames` (extra blocks only),
`network.allowed_schemes` (narrowing only), timeouts, `sources.allow_domains`/`deny_domains`,
research budgets (Phase 3), `review.max_customer_questions`,
`run.active_run_timeout_minutes`, `evals.case_order`, `logging.detail`.

## Eval fixture mode

Offline evals cannot use normal mode, which blocks local files and loopback. Fixture mode
is enabled **only** by `FRA_EVAL_FIXTURES=<dir>` in the environment of the Claude Code
process, and the directory must resolve inside `evals/fixtures/`. Config keys, skill
arguments and in-session env prefixes (blocked by H1) cannot enable it. Scripts refuse to
run when `.active_run`, the manifest and the environment disagree about the mode.

Fixture runs use `evals/runs/`, read fixture files only, and serve fixture pages to the
browser from the reserved origin `http://fixture.invalid/`. Every other request is aborted,
so nothing reaches the network. Fixture-mode output is always publication status
`eval_only`.

Fixtures so far: `evals/fixtures/case-01-award-packages` (straightforward HTML mockup and a
static image), `evals/fixtures/case-09-partial-capture` (missing pages, external and
metadata requests) and `evals/fixtures/case-figma-01-award-packages` (recorded Figma REST
responses, `award.figma.json`, replayed offline; regenerate with
`.venv/bin/python tests/figma_fake.py <dir>`). Recordings follow
`schemas/figma_recording.schema.json`. The evaluation runner (`run_evals.py`, headless `claude -p` with
`--permission-mode dontAsk`, an explicit `--allowedTools` list, `--max-budget-usd`) is
Phase 6.

## Tests

```bash
.venv/bin/python -m pytest
```

Deterministic tests, no model required. They cover locking and parallel appends, hash
chains, the ownership table, mode activation, config restrictions, schemas, SSRF (mocked
DNS and transports), capture request interception, `run_state.py` lifecycle and tamper
detection, every hook rule, and `install_agents.py` (variant selection, drift). Browser
tests are skipped and reported **BLOCKED** when Chromium cannot launch.
The live Figma test runs only when `FIGMA_TOKEN` and `FRA_FIGMA_TEST_URL` (a file you can
read) are set; otherwise it is reported **BLOCKED**. All other Figma tests replay recordings.

Authoring records (BUILD_SPEC §21):
`.claude/agent-tests/mockup-extractor/record.md` (agent-creator sandbox tests) and
`.claude/skills/feature-research-workspace/` (skill-creator e2e evals, skill-auditor
report). Their iteration outputs are gitignored.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `hooks are not active: no hook attestation found` | Claude Code did not load `.claude/settings.json` hooks. Start Claude Code from the repository root, then try again. |
| `setup missing: run install_agents.py` | Run the installer (see Setup). |
| `another run is active (<id>)` | Finish it, or `/feature-research --abort <id>`. |
| Capture `failed` with `BrowserType.launch` | Chromium system libraries are missing: `sudo .venv/bin/playwright install-deps chromium`. |
| Figma `auth_required` | `FIGMA_TOKEN` is not set in the shell that started Claude Code (see "Figma token"). |
| Figma `access_denied` | The token cannot read the file: check it has File content read access and the file is shared with you. |
| Figma `rate_limited` | Retries exhausted; wait and start a new run, or lower `figma_max_frames`. |
| `this run belongs to another Claude Code session` | The run is bound to the session that started it. Use `--resume <run-id>` when it is waiting at a checkpoint or the owner is gone, otherwise `--abort`. |
| `decision provenance check failed` | The answer text passed to `decide` was not found in a message you typed after the checkpoint. Answer again in your own words; the orchestrator must copy them exactly. |
| `blocking question CQ-… has no recorded answer` | Answer that question; blocking questions cannot be skipped. |
| Tamper report | A file changed outside its owner. Read the report (file, owner, last writer). The run cannot continue. Start a new run. |
| Stuck run blocking a session | `/feature-research --abort <run-id>` from any session. Do not delete run files by hand. |
