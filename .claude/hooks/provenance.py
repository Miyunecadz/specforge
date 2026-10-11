"""Decision provenance for `status_rules.py decide` (BUILD_SPEC §11.3, enforced by H1).

A script launched through Bash does not see the hook payload, so this check lives in the
hook. For answers with source "user" it:
  1. decodes the --answers-b64 payload;
  2. reads the session transcript from transcript_path;
  3. finds the most recent `run_state.py await-user <N> --run <run>` Bash call;
  4. collects only human-typed messages after it: transcript entries of type "user" whose
     content is plain text. Entries carrying tool_result blocks, meta entries (skill
     expansions), compact summaries, sidechains, hook context (attachments, system
     reminders) and local command output are skipped, because external content can reach
     the transcript that way;
  5. requires every answer's verbatim text, whitespace-normalised, to appear in one of them.
Anything unreadable or ambiguous is rejected (fail closed).

Answers with source "eval_case_file" are accepted only in fixture mode with
--non-interactive, and every verbatim must appear in the case file.
"""

from __future__ import annotations

import base64
import json
import unicodedata
from pathlib import Path

SKIP_MARKERS = (
    "<system-reminder>", "<command-name>", "<command-message>", "<command-args>", "<local-command-stdout>",
    "<local-command-stderr>", "<bash-input>", "<bash-stdout>", "<bash-stderr>", "<user-prompt-submit-hook>",
    "<task-notification>", "[Request interrupted",
)


class ProvenanceError(Exception):
    pass


def normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _flag(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def is_await_user(tokens: list[str], checkpoint: str, run_id: str) -> bool:
    """tokens as the script sees them: [script_path, 'await-user', N, '--run', R] in any flag order."""
    if len(tokens) < 3 or not tokens[0].endswith("/run_state.py") or tokens[1] != "await-user":
        return False
    return tokens[2].upper() == checkpoint and _flag(tokens, "--run") == run_id


def typed_messages_after_await(transcript: Path, checkpoint: str, run_id: str, split) -> list[str]:
    try:
        lines = transcript.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProvenanceError(f"transcript unreadable: {exc}") from exc
    entries = []
    for n, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except ValueError as exc:
            raise ProvenanceError(f"transcript line {n} is not JSON; cannot verify provenance") from exc
    start = None
    for i, e in enumerate(entries):
        if e.get("type") != "assistant" or e.get("isSidechain"):
            continue
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash"):
                continue
            cmd = (block.get("input") or {}).get("command", "")
            try:
                tokens = split(cmd)
            except ValueError:
                continue
            if is_await_user(tokens[1:], checkpoint, run_id):
                start = i
    if start is None:
        raise ProvenanceError(f"no 'run_state.py await-user {checkpoint} --run {run_id}' call found in the transcript")
    typed: list[str] = []
    for e in entries[start + 1:]:
        if e.get("type") != "user" or e.get("isSidechain") or e.get("isMeta") or e.get("isCompactSummary") \
                or e.get("isVisibleInTranscriptOnly") or "toolUseResult" in e:
            continue
        msg = e.get("message") or {}
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        else:
            continue
        for t in texts:
            if any(marker in t for marker in SKIP_MARKERS):
                continue
            if t.strip():
                typed.append(normalise(t))
    return typed


def decode(b64: str | None) -> dict:
    if not b64:
        raise ProvenanceError("decide without --answers-b64")
    try:
        return json.loads(base64.b64decode(b64, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProvenanceError(f"answers are not base64-encoded UTF-8 JSON: {exc}") from exc


def check(argv: list[str], *, run_id: str, transcript_path: str | None, run_dir: Path, repo: Path,
          fixture_env: bool, split) -> None:
    """argv as the script sees it: [script, 'decide', ...]. Raise ProvenanceError to block."""
    if _flag(argv, "--run") != run_id:
        raise ProvenanceError("decide must name the active run")
    if "--prior" in argv:
        req = json.loads((run_dir / "input/request.json").read_text(encoding="utf-8"))
        if not req.get("prior_decisions"):
            raise ProvenanceError("--prior used but the user supplied no prior decisions file")
        if len(argv) != 4:
            raise ProvenanceError("decide --prior takes no other arguments")
        return
    checkpoint = (_flag(argv, "--checkpoint") or "").upper()
    answers = decode(_flag(argv, "--answers-b64"))
    if not isinstance(answers, dict) or not isinstance(answers.get("answers"), list) or not answers["answers"]:
        raise ProvenanceError("answers payload has no answers")
    if answers.get("checkpoint") != checkpoint:
        raise ProvenanceError("answers checkpoint does not match --checkpoint")
    verbatims = []
    for a in answers["answers"]:
        v = a.get("verbatim") if isinstance(a, dict) else None
        if not isinstance(v, str) or not normalise(v):
            raise ProvenanceError("every answer needs non-empty verbatim text")
        verbatims.append(normalise(v))
    source = answers.get("source")
    if source == "eval_case_file":
        req = json.loads((run_dir / "input/request.json").read_text(encoding="utf-8"))
        case = req.get("non_interactive_case")
        if not fixture_env or not case:
            raise ProvenanceError("eval_case_file answers are accepted only in fixture mode with --non-interactive")
        text = normalise((repo / case["path"]).read_text(encoding="utf-8"))
        missing = [v for v in verbatims if v not in text]
        if missing:
            raise ProvenanceError(f"answer not found in the case file: {missing[0][:60]!r}")
        return
    if source != "user":
        raise ProvenanceError(f"unknown answer source {source!r}")
    if not transcript_path:
        raise ProvenanceError("no transcript_path in the hook payload; cannot verify that the user typed the answers")
    typed = typed_messages_after_await(Path(transcript_path), checkpoint, run_id, split)
    if not typed:
        raise ProvenanceError(f"the user has not typed any message since checkpoint {checkpoint} was presented")
    for v in verbatims:
        if not any(v in t for t in typed):
            raise ProvenanceError(f"verbatim answer does not appear in any message the user typed after "
                                  f"checkpoint {checkpoint}: {v[:60]!r}")
