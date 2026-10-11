#!/usr/bin/env python3
"""capture_mockup.py --run <run-id>: capture the mockup into capture/ (BUILD_SPEC §7 Stage 2, §10).

HTML: Python Playwright. Every browser request (documents, subresources, iframes, popups,
redirects) is intercepted at the browser-context level and served by this script:
- normal mode: fetched through safe_http (SSRF checks on every URL and redirect, pinned IP,
  limits) and returned with route.fulfill, so the browser never connects anywhere itself;
- fixture mode: served from the fixture directory under the reserved origin
  http://fixture.invalid/; every other request is aborted. No network access at all.
Redirects are followed by the script (every hop validated). Only GET/HEAD requests are served; WebSockets and service workers are blocked; forms are
never submitted and nothing is clicked. Same-origin links are followed within the page and
depth limits, except links that look state-changing (logout, delete, ...).

Image: downloaded (or read from the fixture directory) within size and type limits.
Figma: implemented in Phase 1b.

Writes only under capture/. capture/manifest.json is written last. Exit 0 when the
capture is complete or partial, 1 when it failed, 3 when refused.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urldefrag, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import fixtures, fsutil, hashing, modes, paths, runctx, safe_http, schema, urlsafety  # noqa: E402
from _lib.runctx import RunError, now_iso  # noqa: E402

POLICY_BLOCK_CODES = {
    "scheme_not_allowed", "credentials_in_url", "blocked_hostname", "blocked_address", "invalid_url",
    "missing_host", "invalid_host", "dns_failure", "method_not_allowed", "fixture_mode_no_network",
    "outside_fixture_dir", "request_limit", "websocket_blocked", "capture_size_limit",
}
STATE_CHANGING_LINK = re.compile(
    r"(log-?out|sign-?out|delete|remove|destroy|unsubscribe|deactivate|revoke|reset|purchase|checkout|"
    r"confirm|approve|cancel)", re.I)
DROP_RESPONSE_HEADERS = {"content-encoding", "content-length", "transfer-encoding", "set-cookie",
                         "connection", "keep-alive", "strict-transport-security", "alt-svc"}
CONTENT_TYPES = {".html": "text/html", ".htm": "text/html", ".css": "text/css", ".js": "text/javascript",
                 ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg",
                 ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
                 ".svg": "image/svg+xml", ".woff2": "font/woff2", ".woff": "font/woff", ".txt": "text/plain"}


@dataclass
class Recorder:
    blocked: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    limitations: list = field(default_factory=list)
    access_failures: list = field(default_factory=list)
    bytes_total: int = 0

    def block(self, url, page, rtype, reason):
        self.blocked.append({"url": _redact(url), "page": page, "resource_type": rtype, "reason": reason})

    def fail(self, url, page, rtype, reason):
        self.failed.append({"url": _redact(url), "page": page, "resource_type": rtype, "reason": reason})


def _redact(url: str) -> str:
    """Drop query strings and fragments from recorded URLs; they may carry tokens."""
    if url.startswith("data:"):
        return url[:40] + "..."
    parts = urlsplit(url)
    if parts.query:
        return parts._replace(query="[redacted]", fragment="").geturl()
    return parts._replace(fragment="").geturl()


# --------------------------------------------------------------------------- request gate


class RequestGate:
    """Decides and serves every browser request. Testable without a browser via serve()."""

    def __init__(self, mode: modes.Mode, config: dict, recorder: Recorder, *, resolver=None, transport=None):
        self.mode = mode
        self.config = config
        self.rec = recorder
        self.resolver = resolver or urlsafety.system_resolver
        self.transport = transport
        self.policy = safe_http.HttpPolicy.from_config(config, max_bytes=config["capture"]["max_bytes_per_resource"])
        self.current_page: str | None = None
        self.requests_this_page = 0

    def new_page(self, page_id: str) -> None:
        self.current_page = page_id
        self.requests_this_page = 0

    def serve(self, url: str, method: str, rtype: str | None) -> tuple[str, dict]:
        """Return ("fulfill", {status, headers, body}) or ("abort", {reason})."""
        self.requests_this_page += 1
        if self.requests_this_page > self.config["capture"]["max_requests_per_page"]:
            return self._abort(url, rtype, "request_limit")
        if method not in ("GET", "HEAD"):
            return self._abort(url, rtype, "method_not_allowed")
        if self.rec.bytes_total > self.config["capture"]["max_total_capture_bytes"]:
            return self._abort(url, rtype, "capture_size_limit")
        if self.mode.mode == modes.FIXTURE:
            path = fixtures.from_fixture_url(url, self.mode.fixture_dir)
            if path is None:
                code = "fixture_mode_no_network" if urlsplit(url).hostname != fixtures.FIXTURE_HOST else "outside_fixture_dir"
                return self._abort(url, rtype, code)
            if not path.is_file():
                return "fulfill", {"status": 404, "headers": {"content-type": "text/plain"}, "body": b"not found"}
            body = path.read_bytes()
            if len(body) > self.policy.max_bytes:
                return self._abort(url, rtype, "too_large", block=False)
            self.rec.bytes_total += len(body)
            ctype = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
            return "fulfill", {"status": 200, "headers": {"content-type": ctype}, "body": body}
        # Redirects are followed here, every hop re-validated, because Chromium does not
        # follow a redirect handed to it through route.fulfill (the navigation hangs).
        try:
            res = safe_http.fetch(url, self.policy, resolver=self.resolver, transport=self.transport,
                                  follow_redirects=True, method=method)
        except safe_http.FetchBlocked as exc:
            return self._abort(exc.url or url, rtype, exc.code, block=exc.code in POLICY_BLOCK_CODES)
        if res.redirects:
            self.rec.warnings.append(f"{self.current_page}: {_redact(url)} redirected to {_redact(res.final_url)}"
                                     f" ({len(res.redirects)} hop(s), each validated)")
        self.rec.bytes_total += len(res.body)
        headers = {k: v for k, v in res.headers.items() if k not in DROP_RESPONSE_HEADERS}
        return "fulfill", {"status": res.status, "headers": headers, "body": res.body}

    def _abort(self, url, rtype, code, block=True):
        (self.rec.block if block else self.rec.fail)(url, self.current_page, rtype, code)
        return "abort", {"reason": code}

    def playwright_handler(self, route, request) -> None:
        action, data = self.serve(request.url, request.method, request.resource_type)
        if action == "fulfill":
            route.fulfill(status=data["status"], headers=data["headers"], body=data["body"])
        else:
            route.abort("blockedbyclient")


# --------------------------------------------------------------------------- html capture


def _origin(url: str) -> tuple[str, str]:
    p = urlsplit(url)
    return p.scheme, p.netloc.lower()


def _link_followable(href: str, text: str, origin: tuple[str, str]) -> tuple[bool, str | None]:
    if not href.startswith(("http://", "https://")):
        return False, "not an http(s) link"
    if _origin(href) != origin:
        return False, "different origin"
    if STATE_CHANGING_LINK.search(href) or STATE_CHANGING_LINK.search(text or ""):
        return False, "may change state"
    return True, None


def capture_html(start_url: str, gate: RequestGate, config: dict, cap_dir: Path, rec: Recorder,
                 launch: Callable | None = None) -> tuple[list, list]:
    from playwright.sync_api import Error as PwError
    from playwright.sync_api import sync_playwright

    cfg = config["capture"]
    pages: list[dict] = []
    links: list[dict] = []
    origin = _origin(start_url)
    queue: list[tuple[str, int]] = [(urldefrag(start_url)[0], 0)]
    seen: dict[str, str] = {}
    (cap_dir / "pages").mkdir(parents=True, exist_ok=True)
    (cap_dir / "screenshots").mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = (launch or (lambda p: p.chromium.launch(headless=True)))(pw)
        try:
            context = browser.new_context(service_workers="block", accept_downloads=False,
                                          java_script_enabled=True, viewport={"width": 1366, "height": 900})
            context.route("**/*", gate.playwright_handler)
            try:
                context.route_web_socket("**/*", lambda ws: (rec.block(ws.url, gate.current_page, "websocket",
                                                                       "websocket_blocked"), ws.close()))
            except AttributeError:
                rec.limitations.append("WebSocket blocking unavailable in this Playwright version")
            while queue:
                url, depth = queue.pop(0)
                if url in seen:
                    continue
                page_id = f"PAGE-{len(pages) + 1:03d}"
                seen[url] = page_id
                record = {"id": page_id, "url": _redact(url), "final_url": None, "title": None, "depth": depth,
                          "status": "skipped", "http_status": None, "screenshot": None, "text": None,
                          "aria": None, "html": None, "nav_labels": [], "error": None}
                pages.append(record)
                if len([p for p in pages if p["status"] != "skipped"]) >= cfg["max_pages"]:
                    record["error"] = "page limit reached"
                    continue
                gate.new_page(page_id)
                page = context.new_page()
                page.on("popup", lambda p: p.close())
                try:
                    resp = page.goto(url, wait_until="load", timeout=cfg["page_timeout_s"] * 1000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except PwError:
                        pass
                    record["http_status"] = resp.status if resp else None
                    record["final_url"] = _redact(page.url)
                    record["title"] = page.title()
                    stem = page_id.lower()
                    page.screenshot(path=str(cap_dir / "screenshots" / f"{stem}.png"), full_page=True)
                    record["screenshot"] = f"capture/screenshots/{stem}.png"
                    (cap_dir / "pages" / f"{stem}.txt").write_text(page.inner_text("body"), encoding="utf-8")
                    record["text"] = f"capture/pages/{stem}.txt"
                    (cap_dir / "pages" / f"{stem}.html").write_text(page.content(), encoding="utf-8")
                    record["html"] = f"capture/pages/{stem}.html"
                    try:
                        aria = page.locator("body").aria_snapshot()
                        (cap_dir / "pages" / f"{stem}.aria.yaml").write_text(aria, encoding="utf-8")
                        record["aria"] = f"capture/pages/{stem}.aria.yaml"
                    except (PwError, AttributeError) as exc:
                        rec.warnings.append(f"{page_id}: accessibility snapshot unavailable: {exc}")
                    record["nav_labels"] = page.eval_on_selector_all(
                        "nav a, [role=navigation] a, header a",
                        "els => els.map(a => (a.innerText || a.getAttribute('aria-label') || '').trim()).filter(Boolean)")
                    found = page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(a => ({href: a.href, text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 200)}))")
                    record["status"] = "captured" if not (resp and resp.status >= 400) else "failed"
                    if resp and resp.status >= 400:
                        record["error"] = f"HTTP {resp.status}"
                    for link in found:
                        href = urldefrag(link["href"])[0]
                        ok, why = _link_followable(href, link["text"], origin)
                        follow = ok and depth < cfg["max_depth"]
                        if ok and not follow:
                            why = "depth limit"
                        links.append({"from": page_id, "href": _redact(href), "text": link["text"],
                                      "same_origin": _origin(href) == origin, "followed": follow,
                                      "to": None, "_target": href})
                        if why == "may change state":
                            rec.warnings.append(f"{page_id}: did not follow {_redact(href)} (link may change state)")
                        if follow and href not in seen and all(q[0] != href for q in queue):
                            queue.append((href, depth + 1))
                except PwError as exc:
                    record["status"] = "failed"
                    record["error"] = str(exc).splitlines()[0][:300]
                finally:
                    page.close()
            context.close()
        finally:
            browser.close()
    for link in links:
        link["to"] = seen.get(link.pop("_target"))
    return pages, links


# --------------------------------------------------------------------------- image capture


def image_size(data: bytes) -> tuple[int | None, int | None]:
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return w, h
        if data[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", data[6:10])
            return w, h
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and data[12:16] == b"VP8X":
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return w, h
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                seg = struct.unpack(">H", data[i + 2:i + 4])[0]
                i += 2 + seg
    except struct.error:
        pass
    return None, None


EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp", "image/svg+xml": "svg"}


def capture_image(url: str, mode: modes.Mode, config: dict, cap_dir: Path, rec: Recorder, *,
                  resolver=None, transport=None) -> list:
    allowed = config["capture"]["image_content_types"]
    if mode.mode == modes.FIXTURE:
        target = fixtures.resolve_target(url, mode.fixture_dir)
        data = target.read_bytes()
        ctype = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        if ctype not in allowed:
            raise safe_http.FetchBlocked("content_type_not_allowed", ctype, url)
        if len(data) > config["capture"]["max_bytes_per_resource"]:
            raise safe_http.FetchBlocked("too_large", str(len(data)), url)
    else:
        policy = safe_http.HttpPolicy.from_config(config, config["capture"]["max_bytes_per_resource"], allowed)
        res = safe_http.fetch(url, policy, resolver=resolver or urlsafety.system_resolver, transport=transport)
        if res.status >= 400:
            raise safe_http.FetchBlocked("http_error", f"HTTP {res.status}", url)
        data, ctype = res.body, res.content_type
    rec.bytes_total += len(data)
    (cap_dir / "assets").mkdir(parents=True, exist_ok=True)
    rel = f"capture/assets/asset-001.{EXT.get(ctype, 'bin')}"
    fsutil.atomic_write_bytes(cap_dir.parent / rel, data)
    w, h = image_size(data)
    rec.limitations.append("A static image is not an interactive prototype: no flows, states or behaviour "
                           "beyond what the image shows can be observed.")
    return [{"id": "ASSET-001", "url": _redact(url), "path": rel, "content_type": ctype, "bytes": len(data),
             "sha256": hashing.sha256_bytes(data), "width": w, "height": h}]


# --------------------------------------------------------------------------- main


def _method_for(url: str, mode: modes.Mode, config: dict, *, resolver=None, transport=None) -> str:
    from check_url import check

    res = check(url, mode, config, {**os.environ}, resolver=resolver, transport=transport)
    if res["input_type"] == "figma":
        return "figma"
    if res["status"] != "ok":
        raise safe_http.FetchBlocked(res["reason"] or res["status"], "; ".join(res["warnings"]), url)
    return res["input_type"]


def run_capture(ctx: runctx.RunContext, config: dict, *, resolver=None, transport=None, launch=None) -> dict:
    request = json.loads((ctx.run_dir / "input/request.json").read_text(encoding="utf-8"))
    url = request["mockup_url"]
    cap_dir = ctx.run_dir / "capture"
    if cap_dir.exists():
        shutil.rmtree(cap_dir)  # an earlier, incomplete attempt of this stage
    cap_dir.mkdir()
    rec = Recorder()
    pages: list = []
    links: list = []
    assets: list = []
    method = "html"
    try:
        method = _method_for(url, ctx.mode, config, resolver=resolver, transport=transport)
        if method == "figma":
            rec.access_failures.append("Figma capture is implemented in Phase 1b; nothing was captured.")
        elif method == "image":
            assets = capture_image(url, ctx.mode, config, cap_dir, rec, resolver=resolver, transport=transport)
        else:
            gate = RequestGate(ctx.mode, config, rec, resolver=resolver, transport=transport)
            start = url
            if ctx.mode.mode == modes.FIXTURE:
                start = fixtures.to_fixture_url(fixtures.resolve_target(url, ctx.mode.fixture_dir),
                                                ctx.mode.fixture_dir)
            pages, links = capture_html(start, gate, config, cap_dir, rec, launch=launch)
    except (safe_http.FetchBlocked, fixtures.FixtureError) as exc:
        rec.access_failures.append(f"{getattr(exc, 'code', 'fixture_error')}: {exc}")
    except Exception as exc:  # browser launch failures and similar: record, never pretend
        rec.access_failures.append(f"capture error: {type(exc).__name__}: {str(exc).splitlines()[0][:300]}")

    captured = [p for p in pages if p["status"] == "captured"]
    failed = [p for p in pages if p["status"] == "failed"]
    skipped = [p for p in pages if p["status"] == "skipped"]
    if failed:
        rec.limitations.append(f"{len(failed)} page(s) failed to capture: "
                               + ", ".join(f"{p['id']} ({p['error'] or 'error'})" for p in failed))
    if skipped:
        rec.limitations.append(f"{len(skipped)} page(s) were not captured because a limit was reached.")
    if rec.blocked:
        rec.limitations.append(f"{len(rec.blocked)} request(s) were blocked; pages may render incompletely.")
    if rec.failed:
        rec.limitations.append(f"{len(rec.failed)} request(s) failed; pages may render incompletely.")
    if not captured and not assets:
        status = "failed"
    elif failed or skipped or rec.blocked or rec.failed or rec.access_failures:
        status = "partial"
    else:
        status = "complete"
    manifest = {
        "schema_version": 1, "run_id": ctx.run_id, "method": method, "mode": ctx.mode.mode,
        "fixture_dir": ctx.manifest.get("fixture_dir"), "captured_at": now_iso(), "original_url": _redact(url),
        "status": status, "pages": pages, "frames": [], "assets": assets, "links": links,
        "blocked_requests": rec.blocked, "failed_requests": rec.failed, "warnings": rec.warnings,
        "limitations": rec.limitations, "access_failures": rec.access_failures,
        "limits": {k: config["capture"][k] for k in ("max_pages", "max_depth", "max_bytes_per_resource",
                                                     "max_total_capture_bytes", "max_requests_per_page")},
        "totals": {"pages_captured": len(captured), "pages_failed": len(failed), "pages_skipped": len(skipped),
                   "bytes": rec.bytes_total, "requests_blocked": len(rec.blocked)},
    }
    schema.check("capture_manifest", manifest, what="capture/manifest.json")
    fsutil.atomic_write_json(cap_dir / "manifest.json", manifest)
    return manifest


def main(argv: Sequence[str] | None = None, repo: Path | None = None,
         env: Mapping[str, str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    args = ap.parse_args(None if argv is None else list(argv)[1:])
    repo = repo or paths.REPO_ROOT
    env = os.environ if env is None else env
    try:
        ctx = runctx.require_active_run(repo, args.run, env)
        st = ctx.manifest["stages"].get("2")
        if not st or st["status"] != "running":
            raise RunError("stage 2 is not running; run 'run_state.py stage 2 --start' first")
        config = runctx.load_config(repo)
    except RunError as exc:
        print(json.dumps({"ok": False, "refused": str(exc)}))
        return 3
    manifest = run_capture(ctx, config)
    print(json.dumps({"ok": manifest["status"] != "failed", "status": manifest["status"],
                      "method": manifest["method"], "totals": manifest["totals"],
                      "access_failures": manifest["access_failures"], "limitations": manifest["limitations"]},
                     indent=2))
    return 0 if manifest["status"] != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
