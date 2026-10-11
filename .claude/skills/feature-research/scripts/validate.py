#!/usr/bin/env python3
"""validate.py <schema> <file>: validate a JSON, JSONL or YAML file against a schema.

Prints actionable errors and exits non-zero on failure. Never modifies the input.
JSONL files are validated line by line. BUILD_SPEC §10.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import schema  # noqa: E402


def load(path: Path) -> list[tuple[str, object]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        out = []
        for n, raw in enumerate(text.splitlines(), start=1):
            if raw.strip():
                out.append((f"line {n}", json.loads(raw)))
        return out
    if path.suffix in (".yaml", ".yml"):
        import yaml

        return [("document", yaml.safe_load(text))]
    return [("document", json.loads(text))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("schema", help="schema name, e.g. inventory or inventory.schema.json")
    ap.add_argument("file")
    args = ap.parse_args(argv)
    path = Path(args.file)
    try:
        docs = load(path)
    except (OSError, ValueError) as exc:
        print(f"FAIL {path}: cannot read: {exc}")
        return 2
    failed = False
    for where, doc in docs:
        errs = schema.errors(args.schema, doc)
        for e in errs:
            print(f"FAIL {path} {where} {e}")
        failed = failed or bool(errs)
    if not failed:
        print(f"OK {path} against {schema.schema_name(args.schema)} ({len(docs)} document(s))")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
