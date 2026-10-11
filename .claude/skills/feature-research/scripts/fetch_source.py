#!/usr/bin/env python3
"""fetch_source.py --run <run-id> --gap <gap-id> <url>: fetch and save one source (BUILD_SPEC §9.6, §10).

The only way a source enters a run. Owns sources/**, fetch_log.jsonl,
budget/fetches-<gap-id>.json and integrity/fetch_source.json.

- The gap must be approved for research (status_rules.py labels: research_allowed).
- Domain allow/deny lists (config sources.*) are checked before the fetch and against the
  final URL and every redirect hop.
- robots.txt is respected (normal mode). 401/403 on robots.txt or an unreachable robots.txt
  refuse the fetch; other 4xx allow it.
- The per-gap fetch budget is enforced here: every attempt that passes the URL, domain and gap checks is
  counted before any network call (including attempts later refused by robots.txt or a redirect).
- SSRF protections, timeouts, redirect, byte and content-type limits come from safe_http.
- Text is extracted with trafilatura; Playwright (with the capture request gate, so every
  request is re-validated) is used only when the static HTML yields no text.
- Fixture mode: URLs resolve only through evals/cases/<fixture-dir-name>/sources.json; no
  network. "unavailable" entries simulate an inaccessible source; unmapped URLs fail.
- Source id: SRC-<first 8 hex of sha256(final URL)>. Fetched scripts are never executed.
Exit codes: 0 fetched or reused, 1 unavailable, 3 refused.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.robotparser
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import fsutil, hashing, modes, paths, runctx, safe_http, schema, urlsafety  # noqa: E402
from _lib.runctx import RunError, now_iso  # noqa: E402

OWNER = "fetch_source.py"
USER_AGENT = "feature-research-agent"
TEXT_TYPES = ("text/plain",)
SOURCE_TYPES = [
    (("w3.org", "iso.org", "ietf.org", "rfc-editor.org", "whatwg.org", "ecma-international.org", "nist.gov", "owasp.org"), "standard"),
    (("legislation.gov.uk", "eur-lex.europa.eu", "gov.uk", "ico.org.uk", "europa.eu", ".gov"), "regulation"),
    (("material.io", "m3.material.io", "designsystem.digital.gov", "design-system.service.gov.uk", "carbondesignsystem.com",
      "polaris.shopify.com", "atlassian.design", "fluent2.microsoft.design", "developer.apple.com/design"), "design_system"),
    (("developer.mozilla.org", "learn.microsoft.com", "docs.", "developer.", "developers.", "support.", "help."), "official_documentation"),
    (("martinfowler.com", "nngroup.com", "smashingmagazine.com", "web.dev", "baymard.com", "a11yproject.com"), "engineering_publication"),
]


class Refused(RuntimeError):
    pass


def source_id(final_url: str) -> str:
    return "SRC-" + hashing.sha256_text(final_url)[:8]


def canonical(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))


def host_matches(host: str, domain: str) -> bool:
    host, domain = host.lower().rstrip("."), domain.lower().lstrip("*.").rstrip(".")
    return host == domain or host.endswith("." + domain)


def domain_check(url: str, cfg: dict) -> None:
    host = (urlsplit(url).hostname or "").lower()
    for d in cfg["sources"]["deny_domains"]:
        if host_matches(host, d):
            raise Refused(f"domain_denied: {host} matches deny list entry {d}")
    allow = cfg["sources"]["allow_domains"]
    if allow and not any(host_matches(host, d) for d in allow):
        raise Refused(f"domain_not_allowed: {host} is not on the allow list")


def classify(url: str) -> str:
    low = url.lower().split("://", 1)[-1]
    host = low.split("/", 1)[0]
    for needles, kind in SOURCE_TYPES:
        for n in needles:
            if n.startswith(".") and host.endswith(n):
                return kind
            if n.endswith(".") and host.startswith(n):
                return kind
            if "/" in n and low.startswith(n):
                return kind
            if host_matches(host, n):
                return kind
    return "other"


def extract(html: str, url: str) -> tuple[str, str | None, str | None]:
    import trafilatura

    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True, favor_precision=False) or ""
    meta = trafilatura.extract_metadata(html)
    title = getattr(meta, "title", None) if meta else None
    date = getattr(meta, "date", None) if meta else None
    return text.strip(), title, date


def robots_allows(url: str, policy: safe_http.HttpPolicy, resolver, transport) -> tuple[bool, str]:
    p = urlsplit(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    rpol = safe_http.HttpPolicy(**{**policy.__dict__, "max_bytes": 512 * 1024, "allowed_content_types": None})
    try:
        res = safe_http.fetch(robots_url, rpol, resolver=resolver, transport=transport)
    except safe_http.FetchBlocked as exc:
        return False, f"robots.txt unreachable ({exc.code}); not fetching"
    if res.status in (401, 403):
        return False, f"robots.txt returned HTTP {res.status}"
    if 400 <= res.status < 500:
        return True, "no robots.txt"
    if res.status >= 500:
        return False, f"robots.txt returned HTTP {res.status}"
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(res.body.decode("utf-8", "replace").splitlines())
    ok = rp.can_fetch(USER_AGENT, url)
    return ok, "allowed by robots.txt" if ok else "disallowed by robots.txt"


def render_with_browser(url: str, ctx, cfg, resolver, transport) -> str:
    """Playwright fallback for JS-rendered pages, with every request re-validated."""
    import capture_mockup as cm
    from playwright.sync_api import sync_playwright

    rec = cm.Recorder()
    gate = cm.RequestGate(ctx.mode, cfg, rec, resolver=resolver, transport=transport)
    gate.new_page(None)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(service_workers="block", accept_downloads=False)
            context.route("**/*", gate.playwright_handler)
            page = context.new_page()
            page.goto(url, wait_until="load", timeout=cfg["capture"]["page_timeout_s"] * 1000)
            html = page.content()
        finally:
            browser.close()
    return html


# --------------------------------------------------------------------------- fixture mode


def fixture_map(repo: Path, mode: modes.Mode) -> dict:
    case = mode.fixture_dir.name
    path = repo / paths.CASES_REL / case / "sources.json"
    if not path.exists():
        raise Refused(f"fixture mode: no source map at evals/cases/{case}/sources.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    schema.check("fixture_sources", data, what=str(path))
    return data["sources"]


def fixture_fetch(url: str, repo: Path, mode: modes.Mode) -> tuple[bytes, str, int]:
    smap = fixture_map(repo, mode)
    target = smap.get(url) or smap.get(canonical(url))
    if target is None:
        raise Refused("fixture mode: URL is not in the fixture source map (no network access)")
    if target == "unavailable":
        raise safe_http.FetchBlocked("unavailable", "fixture marks this source unavailable", url)
    root = (repo / paths.FIXTURES_REL).resolve()
    f = (repo / target).resolve()
    if root not in f.parents or not f.is_file():
        raise Refused(f"fixture file missing or outside evals/fixtures/: {target}")
    ctype = "text/plain" if f.suffix in (".txt", ".md") else "text/html"
    return f.read_bytes(), ctype, 200


# --------------------------------------------------------------------------- main logic


def fetch(ctx: runctx.RunContext, gap: str, url: str, cfg: dict, *, resolver=None, transport=None) -> dict:
    labels = ctx.run_dir / "status_labels.json"
    routing = json.loads(labels.read_text(encoding="utf-8"))["gap_routing"] if labels.exists() else {}
    if not routing.get(gap, {}).get("research_allowed"):
        raise Refused(f"{gap} is not approved for research")
    st = ctx.manifest["stages"].get("8")
    if not st or st["status"] != "running":
        raise Refused("fetching is allowed only while stage 8 (research) is running")
    url = url.strip()
    if ctx.mode.mode == modes.NORMAL:
        try:
            urlsafety.validate_url(url, allowed_schemes=cfg["network"]["allowed_schemes"],
                                   blocked_hostnames=cfg["network"]["blocked_hostnames"],
                                   resolver=resolver or urlsafety.system_resolver)
        except urlsafety.UrlBlocked as exc:
            raise Refused(f"url_blocked: {exc}") from exc
    domain_check(url, cfg)

    budget_p = ctx.run_dir / f"budget/fetches-{gap}.json"
    limit = cfg["research"]["fetches_per_gap"]
    sources = ctx.run_dir / "sources"
    sources.mkdir(exist_ok=True)

    # Reuse a source already saved in this run (same canonical URL): no network, no budget.
    for meta_p in sources.glob("*.metadata.json"):
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        if meta["available"] and canonical(meta["original_url"]) == canonical(url):
            if gap not in meta["gap_ids"]:
                meta["gap_ids"].append(gap)
                fsutil.atomic_write_json(meta_p, meta)
            _log(ctx, gap, meta["source_id"], url, meta["final_url"], "reused", None, meta["content_sha256"], 0)
            return {"outcome": "reused", "source_id": meta["source_id"], "final_url": meta["final_url"],
                    "title": meta["title"], "path": f"sources/{meta['source_id']}.txt"}

    with fsutil.file_lock(budget_p):
        budget = (json.loads(budget_p.read_text(encoding="utf-8")) if budget_p.exists() else
                  {"schema_version": 1, "kind": "fetches", "run_id": ctx.run_id, "gap_id": gap, "limit": limit,
                   "count": 0, "attempts": []})
        if budget["count"] >= limit:
            raise Refused(f"fetch budget exhausted for {gap} ({budget['count']}/{limit})")
        budget["count"] += 1
        attempt = {"ts": now_iso(), "url": url, "outcome": "refused", "source_id": None, "reason": "in progress"}
        budget["attempts"].append(attempt)
        fsutil.atomic_write_json(budget_p, budget)
    runctx.record_integrity(ctx.run_dir, OWNER, f"budget/fetches-{gap}.json")

    warnings: list[str] = []
    extraction = "trafilatura"
    try:
        if ctx.mode.mode == modes.FIXTURE:
            body, ctype, status = fixture_fetch(url, ctx.repo, ctx.mode)
            final_url, redirects = url, []
            warnings.append("fixture mode: robots.txt not checked (no network)")
        else:
            policy = safe_http.HttpPolicy.from_config(cfg, cfg["research"]["max_source_bytes"],
                                                      cfg["research"]["source_content_types"])
            ok, why = robots_allows(url, policy, resolver or urlsafety.system_resolver, transport)
            if not ok:
                raise Refused(why)
            res = safe_http.fetch(url, policy, resolver=resolver or urlsafety.system_resolver, transport=transport)
            body, ctype, status, final_url, redirects = res.body, res.content_type, res.status, res.final_url, res.redirects
            for hop in redirects:
                domain_check(hop, cfg)
            if status >= 400:
                raise safe_http.FetchBlocked("http_error", f"HTTP {status}", final_url)
        if ctype in TEXT_TYPES:
            text, title, date = body.decode("utf-8", "replace").strip(), None, None
            extraction = "plain_text"
        else:
            html = body.decode("utf-8", "replace")
            text, title, date = extract(html, final_url)
            if not text and ctx.mode.mode == modes.NORMAL:
                warnings.append("static HTML had no extractable text; rendered with Playwright")
                text, title2, date2 = extract(render_with_browser(final_url, ctx, cfg, resolver, transport), final_url)
                title, date = title or title2, date or date2
                extraction = "playwright_trafilatura"
        if not text:
            raise safe_http.FetchBlocked("no_text", "no readable text could be extracted", final_url)
    except Refused as exc:
        _finish_attempt(ctx, budget_p, gap, url, "refused", None, str(exc))
        _log(ctx, gap, None, url, None, "refused", str(exc), None, 0)
        raise
    except (safe_http.FetchBlocked, OSError) as exc:
        reason = f"{getattr(exc, 'code', 'error')}: {exc}"
        sid = source_id(canonical(getattr(exc, "url", None) or url))
        meta = _metadata(ctx, sid, url, getattr(exc, "url", None) or url, None, None, None, None, classify(url), None,
                         False, "none", gap, [reason])
        fsutil.atomic_write_json(sources / f"{sid}.metadata.json", meta)
        _finish_attempt(ctx, budget_p, gap, url, "unavailable", sid, reason)
        _log(ctx, gap, sid, url, getattr(exc, "url", None), "unavailable", reason, None, 0)
        return {"outcome": "unavailable", "source_id": sid, "reason": reason}

    final_c = canonical(final_url)
    sid = source_id(final_c)
    data = (text + "\n").encode("utf-8")
    digest = hashing.sha256_bytes(data)
    fsutil.atomic_write_bytes(sources / f"{sid}.txt", data)
    if redirects:
        warnings.append(f"followed {len(redirects)} redirect(s)")
    meta = _metadata(ctx, sid, url, final_c, title, date, status, ctype, classify(final_c), digest, True, extraction, gap,
                     warnings)
    fsutil.atomic_write_json(sources / f"{sid}.metadata.json", meta)
    _finish_attempt(ctx, budget_p, gap, url, "fetched", sid, None)
    _log(ctx, gap, sid, url, final_c, "fetched", None, digest, len(data))
    return {"outcome": "fetched", "source_id": sid, "final_url": final_c, "title": title,
            "path": f"sources/{sid}.txt", "bytes": len(data), "source_type": meta["source_type"],
            "publication_date": date}


def _metadata(ctx, sid, original, final, title, date, status, ctype, stype, digest, available, extraction, gap, warnings):
    meta = {"schema_version": 1, "source_id": sid, "run_id": ctx.run_id, "original_url": original, "final_url": final,
            "title": title, "fetched_at": now_iso(), "publication_date": date, "http_status": status,
            "content_type": ctype, "source_type": stype, "content_sha256": digest, "available": available,
            "extraction": extraction, "mode": ctx.mode.mode, "fixture_dir": ctx.manifest.get("fixture_dir"),
            "gap_ids": [gap], "warnings": warnings}
    schema.check("source_metadata", meta, what=f"sources/{sid}.metadata.json")
    return meta


def _finish_attempt(ctx, budget_p: Path, gap, url, outcome, sid, reason) -> None:
    with fsutil.file_lock(budget_p):
        budget = json.loads(budget_p.read_text(encoding="utf-8"))
        for att in reversed(budget["attempts"]):
            if att["url"] == url and att["reason"] == "in progress":
                att.update(outcome=outcome, source_id=sid, reason=reason)
                break
        schema.check("budget", budget, what=str(budget_p.name))
        fsutil.atomic_write_json(budget_p, budget)
    runctx.record_integrity(ctx.run_dir, OWNER, f"budget/fetches-{gap}.json")


def _log(ctx, gap, sid, original, final, outcome, reason, digest, nbytes) -> None:
    rec = {"schema_version": 1, "ts": now_iso(), "run_id": ctx.run_id, "gap_id": gap, "source_id": sid,
           "original_url": original, "final_url": final, "outcome": outcome, "reason": reason,
           "content_sha256": digest, "bytes": nbytes, "mode": ctx.mode.mode, "fixture_dir": ctx.manifest.get("fixture_dir")}
    stored = hashing.append_chained(ctx.run_dir / "fetch_log.jsonl", rec)
    schema.check("fetch_log_entry", stored, what="fetch_log.jsonl line")


def main(argv: Sequence[str] | None = None, repo: Path | None = None, env: Mapping[str, str] | None = None,
         resolver=None, transport=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--gap", required=True)
    ap.add_argument("url")
    args = ap.parse_args(None if argv is None else list(argv)[1:])
    repo = repo or paths.REPO_ROOT
    env = os.environ if env is None else env
    try:
        ctx = runctx.require_active_run(repo, args.run, env)
        cfg = runctx.load_config(repo)
        out = fetch(ctx, args.gap, args.url, cfg, resolver=resolver, transport=transport)
    except (RunError, Refused) as exc:
        print(json.dumps({"ok": False, "refused": str(exc)}))
        return 3
    print(json.dumps({"ok": out["outcome"] in ("fetched", "reused"), **out}, indent=2))
    return 0 if out["outcome"] in ("fetched", "reused") else 1


if __name__ == "__main__":
    sys.exit(main())
