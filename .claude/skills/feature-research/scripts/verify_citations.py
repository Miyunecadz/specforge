#!/usr/bin/env python3
"""verify_citations.py --run <run-id>: deterministic citation check (BUILD_SPEC §9.7). Never an LLM call.

For every finding in findings/*.json:
  1. the source id exists in this run AND fetch_log.jsonl has a "fetched" entry for it whose
     content hash matches the saved text and whose run mode matches the manifest;
  2. source metadata exists and the source is not marked unavailable;
  3. the snippet appears in the saved text after conservative normalisation (whitespace,
     quote characters and case only);
  4. finding, gap and source references are valid (finding id scoped to its gap, gap approved
     for research, source id well formed).
Writes citation_check.json. Passing proves the snippet exists in a source that
fetch_source.py fetched, not that it supports the claim (that is Stage 10).
Exit 0 when every finding passed, 1 when any failed, 3 refused.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import fsutil, hashing, paths, runctx, schema  # noqa: E402
from _lib.runctx import RunError, now_iso  # noqa: E402

NORMALISATION = ("Unicode NFC; curly single/double quotes and primes mapped to ' and \"; "
                 "all whitespace runs collapsed to one space; case folded. Nothing else.")
QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
                        "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
                        "«": '"', "»": '"'})
SRC_RE = re.compile(r"^SRC-[0-9a-f]{8}$")


def normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).translate(QUOTES).split()).casefold()


def check(ctx: runctx.RunContext) -> dict:
    run_dir = ctx.run_dir
    labels_p = run_dir / "status_labels.json"
    routing = json.loads(labels_p.read_text(encoding="utf-8"))["gap_routing"] if labels_p.exists() else {}
    log = [e for e in hashing.read_jsonl(run_dir / "fetch_log.jsonl") if e["outcome"] in ("fetched", "reused")]
    if hashing.verify_chain(run_dir / "fetch_log.jsonl"):
        raise RunError("fetch_log.jsonl hash chain is broken; run run_state.py verify")
    results = []
    for fpath in sorted((run_dir / "findings").glob("*.json")):
        doc = json.loads(fpath.read_text(encoding="utf-8"))
        file_gap = fpath.stem
        errs = schema.errors("findings", doc)
        if errs:
            raise RunError(f"{fpath.name} fails findings.schema.json: {errs[0]}")
        for f in doc["findings"]:
            reasons, detail = [], []
            sid = f["source_id"]
            if f["gap_id"] != file_gap or doc["gap_id"] != file_gap or not f["id"].startswith(f"F-{file_gap}-"):
                reasons.append("invalid_artifact_relationship")
                detail.append(f"finding {f['id']} / gap {f['gap_id']} does not belong in findings/{fpath.name}")
            if not routing.get(file_gap, {}).get("research_allowed"):
                reasons.append("invalid_artifact_relationship")
                detail.append(f"{file_gap} is not approved for research")
            if not SRC_RE.match(sid) or "/" in sid:
                reasons.append("invalid_source_reference")
                detail.append(f"bad source id {sid!r}")
            else:
                text_p, meta_p = run_dir / "sources" / f"{sid}.txt", run_dir / "sources" / f"{sid}.metadata.json"
                if not meta_p.exists():
                    reasons.append("source_metadata_missing")
                    detail.append(f"no sources/{sid}.metadata.json")
                    meta = None
                else:
                    meta = json.loads(meta_p.read_text(encoding="utf-8"))
                if not text_p.exists() or (meta is not None and not meta["available"]):
                    reasons.append("source_not_fetched")
                    detail.append(f"sources/{sid}.txt missing or the source is marked unavailable")
                else:
                    digest = hashing.sha256_file(text_p)
                    entries = [e for e in log if e["source_id"] == sid]
                    if not entries:
                        reasons.append("source_not_in_fetch_log")
                        detail.append(f"{sid} has no fetched entry in fetch_log.jsonl")
                    else:
                        if not any(e["content_sha256"] == digest for e in entries):
                            reasons.append("source_hash_mismatch")
                            detail.append("saved text does not match the hash fetch_source.py logged")
                        if not any(e["mode"] == ctx.mode.mode for e in entries) or (meta and meta["mode"] != ctx.mode.mode):
                            reasons.append("source_mode_mismatch")
                            detail.append(f"source fetched in {entries[0]['mode']} mode, run is {ctx.mode.mode}")
                    if normalise(f["snippet"]) not in normalise(text_p.read_text(encoding="utf-8")):
                        reasons.append("snippet_not_found")
                        detail.append("snippet not found in the saved source text")
            results.append({"finding_id": f["id"], "gap_id": f["gap_id"], "source_id": sid, "passed": not reasons,
                            "reasons": sorted(set(reasons)), "detail": "; ".join(detail)})
    passed = sum(r["passed"] for r in results)
    doc = {"schema_version": 1, "run_id": ctx.run_id, "checked_at": now_iso(), "normalisation": NORMALISATION,
           "results": results, "summary": {"checked": len(results), "passed": passed, "failed": len(results) - passed}}
    schema.check("citation_check", doc, what="citation_check.json")
    return doc


def main(argv: Sequence[str] | None = None, repo: Path | None = None, env: Mapping[str, str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    args = ap.parse_args(None if argv is None else list(argv)[1:])
    repo = repo or paths.REPO_ROOT
    env = os.environ if env is None else env
    try:
        ctx = runctx.require_active_run(repo, args.run, env)
        st = ctx.manifest["stages"].get("9")
        if not st or st["status"] != "running":
            raise RunError("stage 9 is not running; run 'run_state.py stage 9 --start' first")
        doc = check(ctx)
    except RunError as exc:
        print(json.dumps({"ok": False, "refused": str(exc)}))
        return 3
    fsutil.atomic_write_json(ctx.run_dir / "citation_check.json", doc)
    failed = [{"finding_id": r["finding_id"], "reasons": r["reasons"]} for r in doc["results"] if not r["passed"]]
    print(json.dumps({"ok": not failed, **doc["summary"], "failed_findings": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
