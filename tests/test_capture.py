"""Capture: request interception decisions (no browser) and end-to-end capture (browser).

Browser tests are skipped, and reported as BLOCKED, when Chromium cannot launch.
"""

from __future__ import annotations

import json
import socket

import httpx
import pytest

import capture_mockup as cm
from _lib import modes, runctx
from conftest import SESSION, add_subagent_event, env_for, need_chromium, run_cli, start_run

PUBLIC = "93.184.215.14"


def cfg():
    return runctx.load_config(cm.paths.REPO_ROOT)


def table_resolver(table):
    def resolve(host, port):
        if host not in table:
            raise OSError("NXDOMAIN")
        return table[host]
    return resolve


PAGE = b"""<html><head><title>Packages</title></head><body>
<h1>Packages</h1>
<img src="http://169.254.169.254/latest/meta-data/iam">
<iframe src="http://10.0.0.5/admin"></iframe>
<img src="https://cdn.example/logo.png">
<a href="/details">Details</a>
<a href="/logout">Log out</a>
<a href="/to-internal">Redirecting link</a>
</body></html>"""


def site_transport():
    def handler(request: httpx.Request):
        host = request.headers["host"]
        path = request.url.path
        if host == "mockup.example":
            if path == "/":
                return httpx.Response(200, headers={"content-type": "text/html"}, content=PAGE)
            if path == "/details":
                return httpx.Response(200, headers={"content-type": "text/html"},
                                      content=b"<html><body><h1>Details</h1><button disabled>Award</button></body></html>")
            if path == "/to-internal":
                return httpx.Response(302, headers={"location": "http://192.168.1.20/secret"})
        if host == "cdn.example":
            return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG\r\n\x1a\n" + b"\0" * 20)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


RESOLVER = table_resolver({"mockup.example": [PUBLIC], "cdn.example": [PUBLIC]})


# --------------------------------------------------------------------------- gate (no browser)


def test_gate_blocks_metadata_and_private_subresources():
    rec = cm.Recorder()
    gate = cm.RequestGate(modes.Mode("normal", None), cfg(), rec, resolver=RESOLVER, transport=site_transport())
    gate.new_page("PAGE-001")
    assert gate.serve("http://169.254.169.254/latest/meta-data/iam", "GET", "image")[0] == "abort"
    assert gate.serve("http://10.0.0.5/admin", "GET", "document")[0] == "abort"
    assert gate.serve("https://cdn.example/logo.png", "GET", "image")[0] == "fulfill"
    reasons = {(b["resource_type"], b["reason"]) for b in rec.blocked}
    assert ("image", "blocked_address") in reasons and ("document", "blocked_address") in reasons
    assert all(b["page"] == "PAGE-001" for b in rec.blocked)


def test_gate_blocks_state_changing_methods():
    rec = cm.Recorder()
    gate = cm.RequestGate(modes.Mode("normal", None), cfg(), rec, resolver=RESOLVER, transport=site_transport())
    gate.new_page("PAGE-001")
    assert gate.serve("https://mockup.example/api/award", "POST", "fetch")[0] == "abort"
    assert rec.blocked[0]["reason"] == "method_not_allowed"


def test_gate_redirect_to_internal_is_blocked_and_recorded():
    rec = cm.Recorder()
    gate = cm.RequestGate(modes.Mode("normal", None), cfg(), rec, resolver=RESOLVER, transport=site_transport())
    gate.new_page("PAGE-001")
    assert gate.serve("https://mockup.example/to-internal", "GET", "document")[0] == "abort"
    assert rec.blocked[-1]["reason"] == "blocked_address"
    assert rec.blocked[-1]["url"].startswith("http://192.168.1.20")


def test_gate_follows_public_redirects():
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<p>new</p>")
    rec = cm.Recorder()
    gate = cm.RequestGate(modes.Mode("normal", None), cfg(), rec, resolver=RESOLVER,
                          transport=httpx.MockTransport(handler))
    gate.new_page("PAGE-001")
    action, data = gate.serve("https://mockup.example/old", "GET", "document")
    assert action == "fulfill" and data["status"] == 200 and data["body"] == b"<p>new</p>"
    assert any("redirected to" in w for w in rec.warnings)


def test_gate_redacts_query_strings():
    rec = cm.Recorder()
    gate = cm.RequestGate(modes.Mode("normal", None), cfg(), rec, resolver=RESOLVER, transport=site_transport())
    gate.new_page("PAGE-001")
    gate.serve("http://10.0.0.5/x?token=SECRET", "GET", "image")
    assert "SECRET" not in json.dumps(rec.blocked)


def test_gate_fixture_mode_makes_no_network_requests(repo, monkeypatch):
    fx = repo / "evals/fixtures/case-a"
    (fx / "index.html").write_text("<p>hi</p>")
    (fx / "../secret.txt").write_text("no")

    def no_network(*a, **k):
        raise AssertionError("network access attempted in fixture mode")
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    rec = cm.Recorder()
    gate = cm.RequestGate(modes.Mode("fixture", fx.resolve()), cfg(), rec)
    gate.new_page("PAGE-001")
    assert gate.serve("http://fixture.invalid/index.html", "GET", "document")[0] == "fulfill"
    assert gate.serve("https://example.com/x.png", "GET", "image")[0] == "abort"
    assert gate.serve("http://169.254.169.254/", "GET", "image")[0] == "abort"
    assert gate.serve("http://fixture.invalid/../secret.txt", "GET", "document")[1].get("status") == 404 \
        or rec.blocked[-1]["reason"] == "outside_fixture_dir"
    assert {b["reason"] for b in rec.blocked} >= {"fixture_mode_no_network"}


def test_state_changing_links_are_not_followed():
    origin = ("https", "mockup.example")
    assert cm._link_followable("https://mockup.example/details", "Details", origin) == (True, None)
    assert cm._link_followable("https://mockup.example/logout", "Log out", origin)[1] == "may change state"
    assert cm._link_followable("https://mockup.example/x", "Delete package", origin)[1] == "may change state"
    assert cm._link_followable("https://other.example/", "x", origin)[1] == "different origin"


def test_image_size_parsing():
    import struct
    png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + struct.pack(">II", 640, 480) + b"\0" * 8
    assert cm.image_size(png) == (640, 480)
    assert cm.image_size(b"GIF89a" + struct.pack("<HH", 10, 20)) == (10, 20)


def test_image_capture_fixture(repo):
    import struct
    fx = repo / "evals/fixtures/case-a"
    (fx / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + struct.pack(">II", 3, 4) + b"\0" * 8)
    run_id = start_run(repo, url="shot.png", fixture="evals/fixtures/case-a")
    import run_state
    from conftest import script_argv
    env = env_for(SESSION, "evals/fixtures/case-a")
    assert run_cli(run_state.main, script_argv(repo, "run_state", "stage", "1", "--run", run_id, "--complete"),
                   repo, env)[0] == 0
    assert run_cli(run_state.main, script_argv(repo, "run_state", "stage", "2", "--run", run_id, "--start"),
                   repo, env)[0] == 0
    ctx = runctx.require_active_run(repo, run_id, env)
    m = cm.run_capture(ctx, cfg())
    assert m["method"] == "image" and m["status"] == "complete" and m["mode"] == "fixture"
    assert m["assets"][0]["width"] == 3 and m["assets"][0]["height"] == 4
    assert any("not an interactive prototype" in x for x in m["limitations"])
    assert not (repo / "runs/.active_run").exists()


# --------------------------------------------------------------------------- browser


def _stage2(repo, run_id, env):
    import run_state
    from conftest import script_argv
    assert run_cli(run_state.main, script_argv(repo, "run_state", "stage", "1", "--run", run_id, "--complete"),
                   repo, env)[0] == 0
    assert run_cli(run_state.main, script_argv(repo, "run_state", "stage", "2", "--run", run_id, "--start"),
                   repo, env)[0] == 0
    return runctx.require_active_run(repo, run_id, env)


def test_browser_normal_mode_blocks_internal_requests(repo, monkeypatch):
    need_chromium()
    run_id = start_run(repo, url="https://mockup.example/")
    ctx = _stage2(repo, run_id, env_for())
    monkeypatch.setattr(cm, "_method_for", lambda *a, **k: "html")
    m = cm.run_capture(ctx, cfg(), resolver=RESOLVER, transport=site_transport())
    blocked = {(b["url"].split("?")[0], b["reason"]) for b in m["blocked_requests"]}
    assert ("http://169.254.169.254/latest/meta-data/iam", "blocked_address") in blocked
    assert ("http://10.0.0.5/admin", "blocked_address") in blocked
    assert any(u.startswith("http://192.168.1.20") for u, _ in blocked)  # public -> internal redirect
    assert m["status"] == "partial"
    assert m["totals"]["pages_captured"] >= 2  # start page and /details
    assert not any(link["followed"] for link in m["links"] if link["href"].endswith("/logout"))


def test_browser_fixture_capture_is_offline(repo, monkeypatch):
    need_chromium()
    fx = repo / "evals/fixtures/case-a"
    (fx / "index.html").write_text('<html><body><h1>Home</h1><a href="next.html">Next</a>'
                                   '<img src="https://example.com/track.png"></body></html>')
    (fx / "next.html").write_text("<html><body><h1>Next</h1></body></html>")
    run_id = start_run(repo, url="index.html", fixture="evals/fixtures/case-a")
    ctx = _stage2(repo, run_id, env_for(SESSION, "evals/fixtures/case-a"))
    real_connect = socket.socket.connect

    def guard(self, addr):
        if isinstance(addr, tuple) and addr[0] not in ("127.0.0.1", "::1"):
            raise AssertionError(f"network access in fixture mode: {addr}")
        return real_connect(self, addr)  # Playwright's local driver pipe only
    monkeypatch.setattr(socket.socket, "connect", guard)
    m = cm.run_capture(ctx, cfg())
    assert m["mode"] == "fixture" and m["totals"]["pages_captured"] == 2
    assert {b["reason"] for b in m["blocked_requests"]} == {"fixture_mode_no_network"}
    assert (ctx.run_dir / "capture/screenshots/page-001.png").exists()


def test_browser_failed_pages_are_listed_as_limitations(repo):
    need_chromium()
    fx = repo / "evals/fixtures/case-a"
    (fx / "index.html").write_text('<html><body><a href="missing.html">Missing</a></body></html>')
    run_id = start_run(repo, url="index.html", fixture="evals/fixtures/case-a")
    ctx = _stage2(repo, run_id, env_for(SESSION, "evals/fixtures/case-a"))
    m = cm.run_capture(ctx, cfg())
    assert m["status"] == "partial" and m["totals"]["pages_failed"] == 1
    assert any("PAGE-002 (HTTP 404)" in x for x in m["limitations"])
    assert not (repo / "runs").exists() or not (repo / "runs/.active_run").exists()
