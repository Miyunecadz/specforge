"""H1 Bash guard (BUILD_SPEC §11.3).

During an active run in this session, every Bash call must be exactly
`<python> <skill>/scripts/<name>.py <args>`: the recorded absolute interpreter, a §10 script
other than install_agents.py and run_evals.py, no environment-variable prefixes, chaining,
pipes, redirection, subshells, substitution, globbing or expansion.

Quoting rules (stricter than the shell, so what we parse is what bash executes):
- single-quoted text may contain any character except a single quote;
- double-quoted text may not contain $, `, \\ or ! (bash expands those inside double quotes);
- unquoted text may contain only letters, digits and _ . / : = , @ % + -
"""

from __future__ import annotations

import re

from _common import Deny, HookContext
from _lib import attest, paths

_UNQUOTED_OK = re.compile(r"[A-Za-z0-9_./:=,@%+\-]")
_DQ_FORBIDDEN = set("$`\\!")
GAP_RE = re.compile(r"^GAP-[0-9]{3,}$")


class ParseError(ValueError):
    pass


def strict_split(command: str) -> list[str]:
    tokens: list[str] = []
    cur: list[str] = []
    in_token = False
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if c in " \t":
            if in_token:
                tokens.append("".join(cur))
                cur, in_token = [], False
            i += 1
        elif c == "'":
            j = command.find("'", i + 1)
            if j < 0:
                raise ParseError("unterminated single quote")
            cur.append(command[i + 1 : j])
            in_token, i = True, j + 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and command[j] != '"':
                if command[j] in _DQ_FORBIDDEN:
                    raise ParseError(f"character {command[j]!r} is not allowed inside double quotes")
                buf.append(command[j])
                j += 1
            if j >= n:
                raise ParseError("unterminated double quote")
            cur.append("".join(buf))
            in_token, i = True, j + 1
        elif _UNQUOTED_OK.fullmatch(c):
            cur.append(c)
            in_token, i = True, i + 1
        else:
            raise ParseError(f"character {c!r} is not allowed outside quotes")
    if in_token:
        tokens.append("".join(cur))
    return tokens


def parse_script_call(command: str, setup: dict) -> tuple[str, list[str]]:
    """Return (script name, argv-as-the-script-sees-it). Raise ParseError if not allowed."""
    tokens = strict_split(command)
    if len(tokens) < 2:
        raise ParseError("expected '<python> <skill>/scripts/<name>.py <args>'")
    if tokens[0] != setup["python"]:
        raise ParseError(f"the interpreter must be exactly {setup['python']}")
    scripts = setup["skill_dir"].rstrip("/") + "/scripts/"
    m = re.fullmatch(re.escape(scripts) + r"([a-z_]+)\.py", tokens[1])
    if not m:
        raise ParseError(f"the script must be {scripts}<name>.py")
    name = m.group(1)
    if name in paths.SETUP_ONLY_SCRIPTS:
        raise ParseError(f"{name}.py may not run while a run is active")
    if name not in paths.RUN_SCRIPTS:
        raise ParseError(f"{name}.py is not a workflow script")
    return name, tokens[1:]


def maybe_attest(command: str, setup: dict | None) -> dict | None:
    """Attestation for run_state.py start/resume/continue, recorded even with no active run."""
    if not setup:
        return None
    try:
        name, argv = parse_script_call(command, setup)
    except ParseError:
        return None
    if name == "run_state" and len(argv) > 1 and argv[1] in attest.ATTESTED_SUBCOMMANDS:
        return {"argv_sha256": attest.argv_digest(argv)}
    return None


def check(ctx: HookContext) -> None:
    command = (ctx.payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        raise Deny("H1", "Bash call without a command string")
    if not ctx.setup:
        raise Deny("H1", "setup file missing (run install_agents.py); Bash is blocked during a run")
    try:
        name, argv = parse_script_call(command, ctx.setup)
    except ParseError as exc:
        raise Deny("H1", f"during an active run Bash may only run workflow scripts: {exc}") from exc

    agent = ctx.agent_type
    if agent is not None:
        installed = ctx.setup.get("researcher_variant")
        if ctx.setup.get("hook_mode") == "identified" and agent == "web-researcher" == installed:
            ok = (
                name == "fetch_source"
                and len(argv) == 6
                and argv[1] == "--run"
                and argv[2] == ctx.run_id
                and argv[3] == "--gap"
                and GAP_RE.match(argv[4])
                and argv[5].startswith(("http://", "https://"))
            )
            if not ok:
                raise Deny(
                    "H1",
                    "web-researcher may only run: <python> <skill>/scripts/fetch_source.py "
                    f"--run {ctx.run_id} --gap GAP-NNN '<url>'",
                )
            return
        raise Deny("H1", f"subagent {agent!r} has no Bash access during a run")

    if name == "status_rules" and len(argv) > 1 and argv[1] == "decide":
        # Decision provenance (§11.3) is implemented with status_rules.py in Phase 2.
        # Until then, fail closed.
        raise Deny("H1", "status_rules.py decide is unavailable until decision provenance is built (Phase 2)")
