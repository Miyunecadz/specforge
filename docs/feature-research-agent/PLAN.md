# Feature Research Agent: Implementation Plan

Date: 2026-10-11. Responds to `BUILD_SPEC.md` Section 2. Section numbers (§) refer to
`BUILD_SPEC.md`.

## Approval and decisions (2026-10-11)

The plan was approved with the answers below. They override anything later in this file
that conflicts with them.

| # | Decision |
|---|---|
| a | Build in place at `/mnt/e/projects/247tech/247-research`; `git init` done (branch `main`). `runs/`, `evals/runs/`, `.venv/`, generated `.claude/agents/` and `.claude/feature-research.local.json` are gitignored. The user will add a remote. |
| b | Shared-rules skill keeps both `user-invocable: false` and `disable-model-invocation: true`. `install_agents.py` embeds the rules verbatim in every agent; a drift test fails on any difference. |
| c | Tool guard adopted as **H5** and added to `BUILD_SPEC.md` §11.3. Scoped to the owning session during a run: blocks Skill, WebFetch and all `mcp__*` tools; blocks WebSearch in the main session; allows the Agent tool only for the nine workflow agents. Tests for each case. |
| d | `uv`-managed `.venv`, `uv.lock` committed. The user runs `sudo .venv/bin/playwright install-deps chromium` themselves. |
| e | Models: **Opus** for gap-analyst, source-verifier, feasibility-analyst, doc-reviewer, eval-citation-grader; **Sonnet** for mockup-extractor, requirements-parser, web-researcher (both variants), question-generator, doc-writer, and the orchestrator during development. Eval caps: **US$10 per case, US$60 per full eval run**; a case that hits its cap is stopped and reported **blocked**. Cases 6–8 run first. |
| f | Phase 1b is built against recorded/mocked Figma REST responses (429 back-off, frame limits, partial labelling tested offline). Live Figma tests are reported **blocked** until a read-only `FIGMA_TOKEN` and test file are supplied. (Answered 2026-10-11.) |
| g | Added test: decision provenance ignores hook-injected text (for example the caveman SessionStart/UserPromptSubmit output). Added to `BUILD_SPEC.md` §11.3 test list. |

**How the CLI enforces the eval budget (probed 2026-10-11, Claude Code 2.1.296):**

- `claude -p --max-budget-usd <amount>` caps total spend for the session **including
  subagents** (probe: the cap tripped after the first subagent's cost was added).
- When reached, the run stops with JSON result `subtype: "error_max_budget_usd"`,
  `is_error: true`, `errors: ["Reached maximum budget ($X)"]`.
- The cap is checked **between turns**, so spend can overshoot by up to one turn's cost
  (probe: $0.00441 against a $0.004 cap). With Opus a single turn can be large.
- `run_evals.py` therefore: passes `--max-budget-usd` = min($10, $60 − spent so far) −
  safety margin (config, default $1); records `total_cost_usd` from each result; treats
  `error_max_budget_usd` as **blocked** for that case; refuses to start a case when the
  remaining run budget is below the margin, reporting the remaining cases as **not run**;
  reports actual spend, including any overshoot, honestly.

Evidence for every capability claim below comes from probes run on 2026-10-11 in a
throwaway project under the session scratchpad, using headless `claude -p` (total probe
cost about US$0.13). Nothing was installed or changed in this repository apart from saving
the spec and this plan.


## Phase 1a implementation notes and deviations (2026-10-11)

Changes from the spec or from this plan's text, each made to enforce a rule more strictly or
to fit a confirmed platform fact.

**Phase 1a gate: approved by the user on 2026-10-11** (468 tests passed, mockup-extractor READY 8/8,
both skills APPROVED by skill-auditor, orchestrator e2e 36/36 plus two HTML runs).

1. **H5 allow-list (confirmed by the user 2026-10-11).** As well as decision (c), H5 blocks every tool not on
   a run allow-list (Read, Glob, Grep, LS, Write/Edit family under H2, Bash under H1, Agent/Task,
   WebSearch, todo tools, ToolSearch). Without it, tools such as Monitor (runs commands),
   Workflow, CronCreate or RemoteTrigger could bypass H1 and H5. AskUserQuestion is also
   blocked, because checkpoints end the turn and answers inside tool results are not counted
   by decision provenance.
2. **Single PreToolUse dispatcher.** `.claude/hooks/guard.py` runs H5 → H1 → H2 (→ H3 → H4 in
   Phase 3), because hooks registered separately run in parallel and §11.3 requires an order.
3. **Hook attestation.** H1 records a digest of every `run_state.py start|resume|continue`
   command, with the session ID, in `.heartbeat`. `run_state.py` refuses without a fresh,
   matching attestation. This proves hooks are loaded and binds the run to the session the
   hooks see.
4. **Session ID for scripts.** Scripts read `CLAUDE_CODE_SESSION_ID`, which Claude Code sets in
   Bash. H1 forbids env prefixes, so a session cannot spoof it.
5. **Hooks run under system `python3`** (stdlib only), not the recorded `<python>`. They share
   `scripts/_lib/` modules that are stdlib-only. Bash calls must still use `<python>`.
6. **Integrity files.** "Continuously updated script files" record their hashes in
   `integrity/<script>.json`, one file per owning script (single writer). These paths were
   added to the ownership table (`scripts/_lib/ownership.py`).
7. **Capture interception is stronger than re-validation.** Every browser request is fetched by
   the script through the SSRF-checked, IP-pinned client and returned with `route.fulfill`
   at the browser-context level (which also covers popups and workers), so Chromium never
   connects anywhere itself. In fixture mode, pages are served from the reserved origin
   `http://fixture.invalid/` instead of `file://`, so every request is intercepted. §16's
   intent (no network, nothing outside the fixture directory) is kept.
   Redirects are followed by the script with every hop re-validated, because Chromium does
   not follow a 3xx handed to it through `route.fulfill` (probed: the navigation hangs).
8. **State-changing links are not followed** (logout, delete, revoke, checkout, …), and are
   recorded as warnings.
9. **Requirements text** is passed as base64. Stage 1 compares the preserved copy with the
   user's text and aborts if they differ (long text is error-prone for the model to encode).
10. **Phase-limited orchestrator.** Reaching an unbuilt stage aborts the run with the reason
    "stages N–16 are not built yet" so the session is released. Aborted runs cannot be
    resumed.
11. **`status_rules.py decide` will take `--run <run-id>`** like every other run script (Phase 2).
12. **Schema additions:** `setup.schema.json` (installer's local file) and
    `integrity.schema.json`.
13. **Eval permission pattern.** `--allowedTools "Bash(<python> <scripts>/*)"` matches; the
    `:*` prefix form did not (probed). `run_evals.py` will use the working form.
14. **Interpreter.** `uv` selected CPython 3.13 for `.venv`; hooks run on system 3.12.
15. **Shared-rules wording.** `<your-agent-name>` placeholders were replaced with a concrete
    example (agent-creator lint).


## Phase 1b implementation notes (2026-10-11)

**Phase 1b gate: approved by the user on 2026-10-11** (486 passed, live Figma test blocked; mockup-extractor
9/9 with T6 Figma; orchestrator e2e 57/57; re-audit APPROVED).

1. Figma client in `scripts/_lib/figma.py`; GET only, token in `X-Figma-Token`, sent only to
   `api.figma.com` (never to the S3 image hosts), scrubbed from error text, never stored.
2. Rate limiting: `Retry-After` honoured, otherwise `figma_backoff_base_s * 2^attempt`; at most
   `figma_max_retries` retries; a `Retry-After` above 120 s is treated as a failure rather
   than waiting.
3. Frames: top-level FRAME/COMPONENT/COMPONENT_SET/SECTION nodes of every page, in file order,
   or only the URL's `node-id` (or its child frames). Node trees fetched in batches of 5,
   trimmed to id, name, type, characters, componentId, visible, bounding box; text layers
   written to `capture/frames/frame-NNN.txt`; prototype reactions become links.
4. Schema changes: capture manifest frames gain `text`; links and request records accept
   FRAME ids; totals gain `frames_captured/failed/skipped`. New `figma_recording.schema.json`.
5. Fixture mode: a `*.figma.json` recording is replayed through the same client via a mock
   transport and a fixed resolver; no DNS or sockets. `tests/figma_fake.py` builds
   recordings (and the eval fixture) from the documented REST response shapes, not from a
   live capture, so field coverage is limited to what the client uses.
6. A blocked or failed frame-image download is recorded in blocked/failed requests and makes
   the capture partial, matching the HTML path.
7. Live Figma tests: **blocked** (no token supplied, decision f).
---

## 1. Current-state findings

**Repository**

- `/mnt/e/projects/247tech/247-research` contains only `build-spec.md` (now also saved as
  `docs/feature-research-agent/BUILD_SPEC.md`) and this plan.
- **Not a Git repository**, and neither is any parent directory.
- No project `.claude/` folder, no `CLAUDE.md` or `AGENTS.md` here or in any ancestor.
  `/mnt/e/.claude/settings.local.json` exists but Claude Code does not load ancestor
  `settings` files for a project, so it has no effect.
- No existing schemas, scripts, templates, or tests. **Nothing implementation-level can be
  reused**; this is a greenfield build.

**Tooling**

| Item | Finding |
|---|---|
| Claude Code | 2.1.296 |
| Python | `/usr/bin/python3` 3.12.3. **No `python` on PATH.** No virtual environment. |
| Python packages (system) | `jsonschema`, `PyYAML` present. `playwright`, `httpx`, `trafilatura`, `pytest` **missing**. |
| Package manager | `uv` available at `~/.local/bin/uv` |
| Node | v22 (not needed by the design) |

**User-level Claude Code configuration that affects this build**

- Global hooks: `caveman` SessionStart and UserPromptSubmit hooks inject style instructions
  into every session, including headless `claude -p`. Their output reaches the transcript
  as hook/attachment entries (relevant to H1 decision provenance and to eval
  reproducibility).
- Enabled plugins relevant to capture/research: `playwright` (browser MCP), `firecrawl`
  (10 web skills), `context7`. A `MCP_DOCKER` server is configured but failing to connect.
- User skills: `skill-auditor`, `agent-creator`, `research`, `find-skills`, `graphify`,
  `grill-me`, `grill-with-docs`; command `planning`. `research`, `planning`, `grill-*`
  are already switched off via `skillOverrides` in `~/.claude/settings.local.json`.
- The user normally runs in `bypassPermissions` mode. Probe confirmed PreToolUse hooks
  still block in that mode, so the hook design holds.

**Reusable for the process (not runtime)**

- `skill-creator` (plugin), `skill-auditor` (with `scripts/check_skill.py --neighbours`),
  `agent-creator`: all installed, so **§21 applies**.

**Unrelated security observation:** `../.mcp.json` (the parent workspace) contains a
plaintext Atlassian API token. It is outside this project and I have not touched it, but
I recommend rotating it and moving it to an environment variable as was done for
`JIRA_API_TOKEN`.

---

## 2. Target location

**Recommendation: build in place, as a new standalone Git repository at
`/mnt/e/projects/247tech/247-research`** (requires `git init`; I will not run it until you
approve).

**Filesystem finding (important):** despite the `/mnt/` path, `/mnt/e` is **not** a
Windows drive mounted through drvfs/9p. Windows has only C: and D:; `/mnt/e` is an
ordinary directory on the WSL root ext4 virtual disk (`/dev/sdd`). Consequences:

- Locking and atomic rename are reliable. Probe: 8 processes × 200 appends each, using
  `O_CREAT|O_EXCL` lock files, produced 1600/1600 unique lines with no loss; `os.replace`
  worked. **Parallel research can stay enabled.**
- These files are **not visible from Windows Explorer as drive E:**. If you expect that,
  this location is misleading.
- Risk: if a Windows E: drive is ever attached, WSL automount (`enabled=true` in
  `/etc/wsl.conf`) would mount it over `/mnt/e` and hide this directory until unmounted.
  Mitigation options: accept the risk, or move the project to
  `~/projects/247tech/247-research` (same filesystem, no shadowing risk). See Open
  Question 1.

`.gitignore` will include `runs/`, `evals/runs/`, `.venv/`, generated `.claude/agents/`
(they embed the absolute interpreter path, so they are machine-specific), and the
machine-specific setup file written by `install_agents.py`.

---

## 3. Overlapping skills

`check_skill.py --neighbours` was run against stub descriptions for both new skills (stubs
lived only in the scratchpad). Highest word-overlap score was 0.05 (`spec-to-backlog`), so
there is no strong lexical overlap. Judgement review of all installed skills:

| Skill / tool | Overlap | Decision | Reason |
|---|---|---|---|
| `research` (user skill) | Web research written to Markdown | **Exclude** | Bypasses `fetch_source.py`, citation checks and budgets. Already off via `skillOverrides`. |
| `firecrawl:*` (10 skills) | Search, scrape, crawl | **Exclude** | Fetching outside `fetch_source.py` breaks §9.6 and §11.1. |
| `playwright` plugin MCP | Browser capture | **Exclude** | §3 requires Python Playwright inside `capture_mockup.py`. |
| `planning` command, `feature-dev` plugin | Planning / feature design | **Exclude** | Different vocabulary and output; `planning` already off. |
| `atlassian:spec-to-backlog` | Consumes specs | **Exclude during runs** | Downstream consumer, not an overlap; usable after a run. |
| `graphify`, `frontend-design`, `caveman` | None functional | **Exclude** | Not relevant. `caveman` style injection noted for evals (item 12). |
| `skill-creator`, `skill-auditor`, `agent-creator` | Authoring | **Reuse as §21 process gates only** | Never loaded at runtime. |

**How conflicting vocabulary is prevented:**

1. Workflow subagents never get the Skill tool (§8), so no skill can load into them.
2. Orchestrator `SKILL.md` states that this workflow's provenance vocabulary, tag format
   and status model override any other skill for the duration of a run (§3).
3. **Proposed addition (needs approval, Open Question 3):** a tool guard inside the H1
   hook module. While a run is active in a session, it blocks `Skill`, `WebFetch`, and all
   `mcp__*` tools for every caller in that session. This turns rule 1–2 from instructions
   into enforcement for the orchestrator too. Other sessions are unaffected.

---

## 4. Platform capability check (§2.4 a–f)

| Check | Result | Evidence | Design consequence |
|---|---|---|---|
| **(a)** Skills as slash commands; `disable-model-invocation` and `user-invocable` honoured | **Yes** | `/probe-cmd alpha beta` as a `-p` prompt ran the skill with its arguments. The model's Skill-tool call on that skill was rejected ("has `disable-model-invocation` set"). `/pre-both` (`user-invocable: false`) produced zero turns. | No `.claude/commands/feature-research.md` fallback needed. |
| **(b)** `skills:` preloading, including a skill with `user-invocable: false` + `disable-model-invocation: true` | **Partial** | Preloading delivered skill content for a plain skill and for `user-invocable: false` alone. It delivered **nothing** for `disable-model-invocation: true`, alone or combined with `user-invocable: false`. | Keep both flags as §3 requires; `install_agents.py` **embeds the shared rules verbatim** in every agent file, with a test that fails on any drift (§8 fallback). See Open Question 2. |
| **(c)** Subagent-scoped hooks, or PreToolUse payload identifying the caller | **Yes, via payload** | PreToolUse payloads from subagent calls carry `agent_id` and `agent_type` (for example `agent_type: "probe-agent"`); main-session calls carry neither. A `hooks:` block in agent frontmatter did **not** fire in the probe. | **Identified mode.** Hooks distinguish orchestrator vs each subagent from `agent_type`. **Install `web-researcher` (Bash variant)**; `web-researcher-fallback` is built and tested but not installed. Hook fallback mode not needed. |
| **(d)** Session ID in payload; same for subagents | **Yes** | Every payload has `session_id`; subagent calls had the same ID as the main session. | Active run is bound to its session ID with no timeout; other sessions in the repo are never restricted. `.heartbeat` is still written (used by `--resume` expiry, §4). |
| **(e)** Hooks under headless `claude -p` with eval permission settings; slash skill as `-p` prompt | **Yes** | Under `--permission-mode dontAsk --allowedTools "..."`, PreToolUse, SubagentStart and UserPromptSubmit hooks all fired. A blocking hook (exit 2) blocked Bash in both `dontAsk` and `bypassPermissions`. With `--setting-sources project`, project hooks still fired. `FRA_EVAL_FIXTURES` set on the parent reached the hook processes. | Evals use `dontAsk` + explicit `--allowedTools` (never `bypassPermissions`). `SubagentStart` (which carries `agent_type`) is used to record subagent invocations in `.hook_events.jsonl`. |
| **(f)** `transcript_path` in PreToolUse payload | **Yes** | Present in every payload. Transcript JSONL: typed user prompts are `type:"user"` entries with string content and no `isMeta`; skill expansions are `isMeta: true`; tool results are lists of `tool_result` blocks; hook context appears as separate `attachment` entries. | H1 decision provenance is implemented as §11.3 describes. Because the transcript format is internal and undocumented, H1 **fails closed** (blocks `decide`) if it cannot parse the transcript, and a test pins the expected format for the installed version. |

**Additional platform fact used by the design:** a hook that exits with any non-zero code
other than 2 is treated by Claude Code as a non-blocking error, which would fail open.
Every hook therefore wraps all logic and returns a deny (exit 2) on any internal error
while a run is active, and `run_state.py start` runs a hook self-test before creating the
run, refusing to start if hooks are not active.

---

## 5. Proposed architecture

```
/feature-research <url> <requirements>          (user-invoked skill; never model-invoked)
        │
        ▼
Orchestrator (main session) ── runs stage loop from SKILL.md, reads references/stage-NN.md
        │   Bash: only <python> <skill>/scripts/<name>.py …   (H1)
        │   Write/Edit: nothing in the run directory          (H2)
        │
        ├─ Scripts (deterministic, own their files): run_state, check_url, capture_mockup,
        │  validate, fetch_source, verify_citations, status_rules, check_spec
        │
        ├─ Subagents (Read/Write only, except web-researcher): extractor, parser,
        │  gap-analyst, web-researcher, source-verifier, feasibility, questions,
        │  doc-writer, doc-reviewer
        │
        └─ Checkpoints 1, 2, 3, 13R: await-user → end turn → user reply →
           continue → status_rules.py decide --answers-b64 (provenance checked by H1)

Hooks (.claude/hooks/, registered in .claude/settings.json):
  H1 Bash guard + tool guard + decision provenance
  H2 Write/Edit ownership guard
  H3 search budget + domain lists (Phase 3)
  H4 eval search stub, fixture mode only (Phase 3)
  SubagentStart recorder → .hook_events.jsonl
  All share one helper for .active_run lookup, heartbeat, hash-chained event log.
```

Data flow follows the §7 table exactly: inputs → `capture/` → `inventory.json` +
`requirements.json` → CP1 → `gaps.json` → CP2 → `findings/` + `sources/` →
`citation_check.json` → `verified_findings.json` → `feasibility.json` →
`questions.json` → CP3 (→ 13R) → `spec.md` → `validation.json` + `review.json` →
`run_summary.json`. Every stage starts with `run_state.py verify`.

---

## 6. Proposed file structure

Matches the §3 layout, with these concrete additions or deviations:

```
.gitignore                                   runs/, evals/runs/, .venv/, .claude/agents/,
                                             .claude/feature-research.local.json
pyproject.toml                               pytest config only (no packaging)
requirements.txt                             pinned: playwright, httpx, trafilatura,
                                             jsonschema, PyYAML, pytest
README.md
docs/feature-research-agent/BUILD_SPEC.md    (saved)
docs/feature-research-agent/PLAN.md          (this file)
.claude/
  settings.json                              hook registration only; no broad permissions
  feature-research.local.json                written by install_agents.py: interpreter path,
                                             hook mode, preload mode, CC version (gitignored)
  hooks/
    _common.py                               active-run lookup, heartbeat writer, event log
                                             (hash chain), O_EXCL lock helper, fail-closed
                                             wrapper
    h1_bash_guard.py                         Bash parse, tool guard, decision provenance
    h2_write_guard.py                        ownership table enforcement
    h3_search_budget.py                      (Phase 3)
    h4_eval_search_stub.py                   (Phase 3)
    record_subagent.py                       SubagentStart → .hook_events.jsonl
  agents/                                    generated only by install_agents.py
  skills/
    feature-research/
      SKILL.md                               stage loop, checkpoint protocol, hard rules
      config.yaml
      references/stage-01.md … stage-16.md, stage-13r.md
      agents-src/                            one .md per agent, both researcher variants,
                                             eval-citation-grader
      scripts/
        _lib/  locking.py, atomic.py, hashing.py, modes.py, urlsafety.py, schema.py
        run_state.py  install_agents.py  check_url.py  capture_mockup.py  validate.py
        fetch_source.py  verify_citations.py  status_rules.py  check_spec.py
        run_evals.py
      schemas/                               all §5 schemas, introduced per phase
      templates/spec-template.md
      checklists/gap-checklist.md
    feature-research-subagent-rules/SKILL.md
evals/  cases/  fixtures/  results/  runs/
tests/  test_<script>.py, test_hooks_*.py, test_fixture_mode.py, conftest.py
```

Deviation from §3: shared script helpers live in `scripts/_lib/` to keep the single-writer
and locking logic in one place. `_lib` is not callable through H1 (only top-level §10
scripts are allowed).

---

## 7. Agent responsibilities

All agents: frontmatter `tools:` is the complete allowance; no Skill, WebFetch, browser or
MCP tools; shared rules embedded verbatim; model `inherit` initially (Open Question 5).
H2 restricts each agent's writes to its own paths (identified mode).

| Agent | Tools | Inputs | Output (only writer) | Boundaries |
|---|---|---|---|---|
| mockup-extractor | Read, Write | capture manifest, text, screenshots, Figma trees | `inventory.json`, `warnings/mockup-extractor.json` | observed only; ambiguous behaviours recorded; no backend inference |
| requirements-parser | Read, Write | `input/requirements.md`, prior decisions | `requirements.json` | customer words only; never upgrades priority; ambiguity → question |
| gap-analyst | Read, Write | inventory, requirements, registry, decisions, checklist | `gaps.json` | no solutions; routes research/customer/both |
| web-researcher (installed) | WebSearch, Read, Write, Bash limited by H1 to the exact `fetch_source.py --run --gap <url>` form | approved research gaps, questions, config | `findings/<gap-id>.json` | never writes `sources/`; budgets by H3 and `fetch_source.py` |
| web-researcher-fallback (built, not installed) | WebSearch, Read, Write | same | `fetch_requests/<gap-id>.json`, then findings | no Bash |
| source-verifier | Read, Write | findings that passed §9.7, sources, gaps | `verified_findings.json` | never strengthens claims |
| feasibility-analyst | Read, Write | requirements, registry, decisions, gaps, kept findings, inventory, repo docs | `feasibility.json` | never invents architecture; §9.9 classification mandatory |
| question-generator | Read, Write | customer/both gaps, conflicting/unknown items, stale items, unknowns | `questions.json` | max from config; recommendations only from kept findings |
| doc-writer | Read, Write | all artifacts, `status_rules.py labels` output, template | `spec.md` | line format; placement exactly as derived |
| doc-reviewer | Read, Write | spec and every artifact | `review.json` | independent; unverifiable = fail |
| eval-citation-grader (evals only) | Read, Write | findings + sources from eval runs | grader output under `evals/results/` | never installed for normal runs |

---

## 8. Data contracts and file ownership

The §5 ownership table is adopted **unchanged**. Additions:

| Path | Single writer | Notes |
|---|---|---|
| `.claude/feature-research.local.json` | `install_agents.py` | not a run file; H1 blocks `install_agents.py` during a run |
| `.claude/agents/*.md` | `install_agents.py` | generated; H2 blocks Write/Edit there during a run |
| `evals/results/*.json` | `run_evals.py` | outside any run |

Schemas: all 34 from §5, each with `schema_version`, sharing `common.schema.json`. I do not
plan to merge any trivial schemas unless duplication appears; any merge will be documented
in the README. Every content schema sets `additionalProperties: false` and explicitly
forbids `approval`, `issues`, `verification`, `stale`.

Hash recording: stage outputs at `stage --complete`; continuously updated script files via
the shared `hashing.py` helper on every write; append-only files via per-line hash chains
(`prev_hash` field).

---

## 9. Status model

Implemented exactly as §6 in `status_rules.py`:

- Registry entries: id, kind, provenance, source artifact, approval, issues, decision IDs,
  stale + stale reason, verification (findings only).
- Transition table encoded as data; every row and every rejected transition has a test.
- Initial approval: `approved` only for `user_decision` provenance with its DEC; everything
  else `not_reviewed`.
- Stale: set only by `apply`; unapproved stale → `superseded`; approved stale stays
  approved; cleared only by a re-confirming DEC.
- Verification: `pending` → `citation_failed` (from `citation_check.json`) → `kept` /
  `dropped` (from `verified_findings.json`). No DEC can approve a non-`kept` finding.
- Labels and placement: `labels` subcommand outputs the §6 first-match label and placement
  for every item, consumed by doc-writer and `check_spec.py`.
- ID allocation per the §6 table; `register` rejects duplicates and enforces the §9.9
  mapping. `decide` allocates DEC, decision-originated REQ and GAP IDs.
- `decide` decodes base64 UTF-8 JSON; tests include apostrophes, quotes, newlines,
  non-ASCII and a long multi-paragraph answer.

---

## 10. Security design

- **URLs (§11.1):** one `urlsafety.py` used by `check_url.py`, `capture_mockup.py` and
  `fetch_source.py`: http/https only; resolve and reject loopback, private, link-local,
  CGNAT, multicast, reserved and metadata addresses (IPv4 and IPv6, including mapped
  forms); re-validate after every redirect; httpx connects to the validated IP with the
  original Host/SNI to resist DNS rebinding; redirect, timeout, byte and content-type
  limits; fail closed. Tests use mocked DNS and route handlers only.
- **Playwright:** `page.route("**/*")` re-validates every request (subresources, iframes,
  redirects); blocked requests recorded in the manifest; no form submission or clicks
  beyond link following. Service workers disabled.
- **Hooks:** H1, H2 (Phase 1a), H3, H4 (Phase 3), subagent recorder. Identified mode, so:
  - orchestrator: Bash only `<python> <skill>/scripts/<allowed>.py …`; no Write/Edit
    under the run directory;
  - web-researcher: Bash only the exact `fetch_source.py` form; writes only its findings;
  - other subagents: no Bash; write only their owned paths.
  - Proposed tool guard (Open Question 3): block Skill, WebFetch and `mcp__*` during a run.
  - Fail closed on any internal error; `run_state.py start` performs a hook self-test.
- **`.active_run` / `.heartbeat`:** `.active_run` (run ID, mode, session ID, start time)
  written only by `run_state.py`; hooks apply restrictions only when the payload
  `session_id` matches. Heartbeat refreshed by hooks on every guarded call; used by
  `--resume` to decide whether another session may still own the run. `--abort` clears a
  stuck run.
- **Tamper detection:** as §5 and item 8; `verify` at every stage start, `continue`, and
  `resume`; agent-stage completion requires a matching SubagentStart record.
- **Decision provenance:** H1 decodes `--answers-b64`, reads `transcript_path`, finds the
  latest `await-user <N>` Bash call, then requires every verbatim answer to appear
  (whitespace-normalised) in a later `type:"user"`, string-content, non-`isMeta`,
  non-`tool_result` entry. Fails closed if the transcript is missing or unparsable.
- **Eval fixture mode:** activated only by `FRA_EVAL_FIXTURES` in the process environment,
  path must resolve inside `evals/fixtures/`; own run root `evals/runs/`; no network at all
  (capture loads only `file://` inside the fixture dir; fetch uses the case URL map); H1
  rejects env-var prefixes so a session cannot enable it; all scripts refuse on mode
  mismatch; specs always `eval_only`.
- **Secrets:** `FIGMA_TOKEN` read from the environment only; redaction helper on all log
  and manifest writes; tests assert no token appears in any run file.

**Residual risks to document in the README:**

1. The orchestrator, holding the user's full permissions, is the trust root; the hooks
   constrain it during a run but not before `start` or after `end`.
2. The transcript format is internal; a Claude Code update could break provenance checks
   (they fail closed, which blocks runs until updated, rather than failing open).
3. If `python3` itself is missing, hook commands fail with a non-2 exit and Claude Code
   treats that as non-blocking. The start-time self-test mitigates this for new runs.
4. Interpretations of answers cannot be checked mechanically; they are shown back at the
   next checkpoint and in the report.

---

## 11. Failure handling, resume, and abort

- **Stage failure:** schema-invalid output → one retry with validation errors → if still
  invalid, stop dependent stages, record in `log.jsonl`, report, leave run resumable.
- **Script failure:** non-zero exit recorded with reason; capture/fetch partials recorded
  as partial, never as complete.
- **Missing auth (Figma):** stop dependent capture at Stage 1 with setup instructions.
- **Blocking review failures after two rounds:** `not_fully_validated`, issues listed.
- **Tamper:** stop with a tamper report naming file, owner, last writer.
- **Resume:** allowed only if the run is at `await-user` or its heartbeat has expired;
  `run_state.py resume` re-verifies every artifact against schema and hash, marks invalid
  or stale items, rebinds `.active_run` to the new session, resumes at the first incomplete
  or stale stage, or re-presents the pending checkpoint with recorded answers.
- **Abort:** marks the manifest `aborted`, logs the reason, removes `.active_run` if it
  refers to this run, preserves all artifacts; aborted runs cannot be resumed.

---

## 12. Evaluation plan

**Deterministic (pytest, no model):** every script, every hook (all §11.3 test cases),
locking/parallel append, SSRF (mocked DNS, `img`/`iframe` to 169.254.169.254 and a private
address, public→internal redirect), fixture-mode isolation and activation tests,
`status_rules.py` transition/stale/verification/placement tests, `check_spec.py` against
good and bad spec samples, shared-rules drift test, researcher-variant test.

**Pipeline evals:** `run_evals.py` runs cases one at a time:

```
FRA_EVAL_FIXTURES=<evals/fixtures/case-dir> claude -p "/feature-research --non-interactive …" \
  --permission-mode dontAsk \
  --allowedTools "Read Write Agent WebSearch Bash(<python> <skill>/scripts/*)" \
  --setting-sources project \
  --output-format stream-json
```

- `dontAsk` denies anything not explicitly allowed; it does not skip checks. Probe
  confirmed hooks fire under it, and under `--setting-sources project`.
- `--setting-sources project` excludes user-level hooks and plugins (for example the
  caveman style hook, firecrawl, playwright MCP) so eval runs are reproducible. Whether this
  keeps login auth working will be confirmed in Phase 6; if not, evals run with user
  settings and the deviation is documented.
- A test confirms H1–H4 fire under exactly these flags.
- Answer matching by topic keywords plus affected REQ ID or gap description; unmatched or
  multiply-matched questions stay unanswered and are recorded.
- Metrics as §16, each with a stated denominator, never collapsed; semantic citation
  grader reported separately.

**Estimated cost and runtime (uncertain, to be measured in Phase 1a/3):** one case runs
16 stages with about 9–12 subagent calls plus a long orchestrator context.

| Model for orchestrator + agents | Per case | Full 10-case run |
|---|---|---|
| Opus (current default) | roughly US$5–15, 20–45 min | roughly US$50–150, 4–7 h |
| Sonnet | roughly US$1.5–5, 15–35 min | roughly US$15–50, 3–6 h |

I will replace these with measured numbers from the first fixture runs and report them at
the Phase 3 gate.

---

## 13. Open questions (need your decision)

1. **Location and Git.** Approve building in place at `/mnt/e/projects/247tech/247-research`
   with `git init`? Note it is on the WSL ext4 disk, not a Windows E: drive (not visible
   from Windows; could be hidden if an E: drive is attached later). Alternative:
   `~/projects/247tech/247-research`. *Recommendation: in place, unless you need Windows
   access or expect an E: drive.*
2. **Shared rules loading.** Preloading does not work with `disable-model-invocation: true`.
   Keep both flags and embed the rules verbatim in each agent (spec fallback, drift test),
   or drop `disable-model-invocation` so preloading works (the model could then load the
   rules in ordinary sessions)? *Recommendation: keep both flags, embed.*
3. **Tool guard.** Approve adding Skill, WebFetch and `mcp__*` blocking to H1 during an
   active run (owning session only)? It goes slightly beyond §11.3's text but enforces
   §3/§8/§11.5. *Recommendation: yes.*
4. **Dependencies.** Approve a `uv`-managed `.venv` in the project with pinned
   `requirements.txt`? Playwright Chromium on WSL needs system libraries, which require you
   to run `! sudo .venv/bin/playwright install-deps chromium` once (I cannot run sudo).
5. **Models and eval budget.** Subagents `inherit` the session model (Opus) by default.
   Do you want a cheaper model for any agent, and what spend ceiling should a full eval run
   respect?
6. **Figma (Phase 1b).** Do you have a read-only `FIGMA_TOKEN` and a test file? Without
   them, Phase 1b live tests will be reported as **blocked**; mocked API tests still run.

---

## 14. Implementation phases

Every phase gate: run tests and applicable evals, show real results including failures,
list §-sections satisfied / partial / remaining, list limitations, show §21 gate results,
wait for approval.

**Phase 1a: Foundation, security, HTML/image capture**
- Setup: `git init`, `.gitignore`, `.venv`, `requirements.txt`, pytest config.
- `install_agents.py` (interpreter resolution, identified mode, embedded rules, single
  researcher variant).
- Orchestrator skill (`disable-model-invocation: true`, SKILL.md ≤500 lines,
  `references/` skeleton) and shared-rules skill; built with skill-creator, audited with
  skill-auditor (§21.1–2).
- `config.yaml` + Phase 1a schemas; `_lib` locking/atomic/hashing; parallel-append test.
- `run_state.py` (start/end/abort/verify/stage/log, `.active_run`, tamper detection, hook
  self-test).
- Hooks H1, H2, subagent recorder, heartbeat; tests for every script-owned and hook-owned
  path, interpreter mismatch, env prefixes, session mismatch, expiry, no active run.
- `urlsafety.py`, `check_url.py` with SSRF tests; fixture mode for capture with isolation
  tests; `capture_mockup.py` HTML + image with `page.route`.
- `mockup-extractor` (agent-creator, with injection and missing-input sandbox tests).
- Two local fixtures.
- *Deliverable:* live and fixture capture, traceable inventory, tested hooks, ownership,
  tamper detection, SSRF and fixture restrictions.

**Phase 1b: Figma capture**
- Figma REST client: read-only token, 429 + `Retry-After` backoff, `figma_max_frames`,
  partial labelling; mocked-API tests; live test if a token is supplied.
- *Deliverable:* Figma produces the same inventory contract.

**Phase 2: Requirements, gaps, status, resume, abort**
- Phase 2 schemas; `status_rules.py` register/decide/labels + full transition, placement
  and encoding tests; H1 decision provenance with transcript tests (forged, tool-result,
  genuine, special characters).
- `requirements-parser`, `gap-analyst` (agent-creator), checklist, Checkpoints 1 and 2,
  `--resume`, `--abort`. Re-audit SKILL.md/references.
- *Deliverable:* tracked requirements and gaps, decisions only via `decide`, pause/resume/
  abort.

**Phase 3: Research and verification**
- Phase 3 schemas; `fetch_source.py` (httpx + trafilatura, robots.txt, budgets, fixture
  map, fetch log); H3, H4 (with H3-before-H4 test); `verify_citations.py`;
  `status_rules.py verification`; both researcher variants (installed: `web-researcher`);
  `source-verifier`; prompt-injection tests; first measured cost/runtime.
- *Deliverable:* verified findings within budgets, offline-runnable.

**Phase 4: Feasibility and decisions**
- Phase 4 schemas; `feasibility-analyst` with §9.9 mapping; `question-generator`;
  Checkpoints 3 and 13R.
- *Deliverable:* prioritised questions, recorded decisions, re-confirmation path.

**Phase 5: Specification and review**
- Phase 5 schemas; template; `doc-writer`; ASM-W registration; `check_spec.py`;
  `doc-reviewer`; revision loop; post-15 13R re-run; publication status incl. `eval_only`.
- *Deliverable:* reviewed spec with honest status.

**Phase 6: Evaluation and change management**
- Phase 6 schemas; `run_evals.py` (headless flags above, isolation, non-interactive
  restrictions, answer matching); `eval-citation-grader`; all 10 cases; metrics;
  `status_rules.py apply` + change-impact; run summary; README completed and checked
  against the implementation.
- *Deliverable:* repeatable offline evaluation and documented limitations. Cases 6–8 must
  pass before use on real customer input.
