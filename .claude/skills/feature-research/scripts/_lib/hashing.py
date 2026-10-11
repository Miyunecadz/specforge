"""Content hashes and hash-chained JSONL files (BUILD_SPEC §5, Tamper detection). Stdlib only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import fsutil

GENESIS = "0" * 64


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def line_hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "line_hash"}
    return sha256_text(canonical(body))


def _last_line(path: Path) -> str | None:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return None
    if size == 0:
        return None
    with open(path, "rb") as fh:
        block = 4096
        data = b""
        pos = size
        while pos > 0:
            step = min(block, pos)
            pos -= step
            fh.seek(pos)
            data = fh.read(step) + data
            stripped = data.rstrip(b"\n")
            if b"\n" in stripped:
                return stripped.rsplit(b"\n", 1)[1].decode("utf-8")
        stripped = data.rstrip(b"\n")
        return stripped.decode("utf-8") if stripped else None


def last_hash(path: Path | str) -> str:
    line = _last_line(Path(path))
    if line is None:
        return GENESIS
    return json.loads(line)["line_hash"]


def append_chained(path: Path | str, record: dict) -> dict:
    """Append record with prev_hash/line_hash under the file's lock. Returns the stored record."""
    path = Path(path)
    with fsutil.file_lock(path):
        rec = {k: v for k, v in record.items() if k not in ("prev_hash", "line_hash")}
        rec["prev_hash"] = last_hash(path)
        rec["line_hash"] = line_hash(rec)
        fsutil.append_line_unlocked(path, canonical(rec))
    return rec


def read_jsonl(path: Path | str) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                out.append(json.loads(raw))
    return out


def verify_chain(path: Path | str) -> list[str]:
    """Return a list of problems; empty means the chain is intact (or the file is absent)."""
    path = Path(path)
    if not path.exists():
        return []
    problems: list[str] = []
    prev = GENESIS
    with open(path, encoding="utf-8") as fh:
        for n, raw in enumerate(fh, start=1):
            if not raw.strip():
                problems.append(f"line {n}: empty line")
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                problems.append(f"line {n}: not valid JSON")
                return problems
            if rec.get("prev_hash") != prev:
                problems.append(f"line {n}: prev_hash does not match line {n - 1}")
            if rec.get("line_hash") != line_hash(rec):
                problems.append(f"line {n}: line_hash does not match content")
            prev = rec.get("line_hash", "")
    return problems
