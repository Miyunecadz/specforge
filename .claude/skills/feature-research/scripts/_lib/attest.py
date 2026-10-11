"""Hook attestation shared by H1 and run_state.py (stdlib only).

When H1 sees `<python> run_state.py start|resume|continue ...` it records a digest of the
exact argv in .heartbeat. run_state.py recomputes the digest from its own sys.argv and
refuses unless a matching, fresh attestation from the same session exists. This proves
that hooks are active and that the run is bound to the session the hooks see.
"""

from __future__ import annotations

from . import hashing

ATTESTED_SUBCOMMANDS = ("start", "resume", "continue")
MAX_AGE_SECONDS = 120


def argv_digest(argv: list[str]) -> str:
    """argv as seen by the script: [script_path, arg1, ...]."""
    return hashing.sha256_text(hashing.canonical(list(argv)))
