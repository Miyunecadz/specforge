"""Figma capture against recorded REST responses; no network, no real token (BUILD_SPEC §4, §7, Phase 1b)."""

from __future__ import annotations

import copy
import json
import socket

import httpx
import pytest

import capture_mockup as cm
import figma_fake
import run_state
from _lib import figma, runctx
from conftest import SESSION, env_for, run_cli, script_argv, start_run

FX = "evals/fixtures/case-a"
TOKEN = "figd_SECRET_TOKEN_value_123"


def cfg(**capture):
    c = copy.deepcopy(runctx.load_config(cm.paths.REPO_ROOT))
    c["capture"].update(capture)
    return c


def fixture_run(repo, monkeypatch=None, **build):
    path = figma_fake.build(repo / FX, **build)
    run_id = start_run(repo, url=path.name, fixture=FX)
    env = env_for(SESSION, FX)
    assert run_cli(run_state.main, script_argv(repo, "run_state", "stage", "1", "--run", run_id, "--complete"), repo, env)[0] == 0
    assert run_cli(run_state.main, script_argv(repo, "run_state", "stage", "2", "--run", run_id, "--start"), repo, env)[0] == 0
    return runctx.require_active_run(repo, run_id, env)


def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)


# --------------------------------------------------------------------------- URL parsing


@pytest.mark.parametrize("url,key,node", [
    ("https://www.figma.com/design/AbCdEfGhIjKlMnOp1234/Award", "AbCdEfGhIjKlMnOp1234", None),
    ("https://figma.com/file/AbCdEfGhIjKlMnOp1234/Award?node-id=1-3", "AbCdEfGhIjKlMnOp1234", "1:3"),
    ("https://www.figma.com/proto/AbCdEfGhIjKlMnOp1234/x?node-id=12%3A34&t=abc", "AbCdEfGhIjKlMnOp1234", "12:34"),
])
def test_parse_url(url, key, node):
    t = figma.parse_url(url)
    assert (t.file_key, t.node_id) == (key, node)


@pytest.mark.parametrize("url", ["https://evil.example/design/AbCdEfGhIjKlMnOp1234/x",
                                 "https://www.figma.com/community/file/123",
                                 "https://www.figma.com/design/AbCdEfGhIjKlMnOp1234/x?node-id=1;rm"])
def test_parse_url_rejects(url):
    with pytest.raises(figma.FigmaError):
        figma.parse_url(url)


# --------------------------------------------------------------------------- fixture mode


def test_fixture_capture_complete_and_offline(repo, monkeypatch):
    ctx = fixture_run(repo)
    no_network(monkeypatch)
    m = cm.run_capture(ctx, cfg())
    assert m["method"] == "figma" and m["status"] == "complete" and m["mode"] == "fixture"
    assert m["totals"]["frames_captured"] == 3 and m["totals"]["pages_captured"] == 0
    f1 = m["frames"][0]
    assert f1["name"] == "Packages / List" and f1["page_name"] == "Packages" and f1["node_id"] == "1:2"
    for f in m["frames"]:
        for key in ("image", "node_tree", "text"):
            assert (ctx.run_dir / f[key]).is_file(), (f["id"], key)
    assert "Supplier packages" in (ctx.run_dir / f1["text"]).read_text()
    edges = {(link["from"], link["to"]) for link in m["links"]}
    assert ("FRAME-001", "FRAME-002") in edges and ("FRAME-002", "FRAME-003") in edges
    assert ("FRAME-002", "FRAME-001") in edges
    tree = json.loads((ctx.run_dir / m["frames"][2]["node_tree"]).read_text())
    assert any("disabled" in c["name"] for c in tree["children"])
    assert run_cli(run_state.main, script_argv(repo, "run_state", "stage", "2", "--run", ctx.run_id, "--complete"),
                   repo, env_for(SESSION, FX))[0] == 0


def test_frame_limit_makes_capture_partial(repo):
    ctx = fixture_run(repo, extra_frames=4, max_frames=3)
    m = cm.run_capture(ctx, cfg(figma_max_frames=3))
    assert m["status"] == "partial"
    assert (m["totals"]["frames_captured"], m["totals"]["frames_skipped"]) == (3, 4)
    assert all(f["error"].startswith("frame limit") for f in m["frames"] if f["status"] == "skipped")
    assert any("figma_max_frames=3" in x for x in m["limitations"])


def test_rate_limit_honours_retry_after(repo):
    ctx = fixture_run(repo, rate_limit=2, retry_after="1.5")
    waits = []
    m = cm.run_capture(ctx, cfg(), sleep=waits.append)
    assert waits == [1.5, 1.5] and m["status"] == "complete"
    assert sum("HTTP 429" in w for w in m["warnings"]) == 2


def test_rate_limit_backoff_without_retry_after(repo):
    ctx = fixture_run(repo, rate_limit=2, retry_after=None)
    waits = []
    m = cm.run_capture(ctx, cfg(figma_backoff_base_s=2), sleep=waits.append)
    assert waits == [2, 4] and m["status"] == "complete"


def test_rate_limit_retries_exhausted_is_a_capture_failure(repo):
    ctx = fixture_run(repo, rate_limit=5)
    waits = []
    m = cm.run_capture(ctx, cfg(figma_max_retries=3), sleep=waits.append)
    assert len(waits) == 3 and m["status"] == "failed"
    assert m["access_failures"][0].startswith("rate_limited")


def test_excessive_retry_after_gives_up(repo):
    ctx = fixture_run(repo, rate_limit=1, retry_after="600")
    waits = []
    m = cm.run_capture(ctx, cfg(), sleep=waits.append)
    assert waits == [] and m["status"] == "failed" and "Retry-After" in m["access_failures"][0]


def test_access_denied(repo):
    ctx = fixture_run(repo, denied=True)
    m = cm.run_capture(ctx, cfg())
    assert m["status"] == "failed" and m["access_failures"][0].startswith("access_denied")


def test_invalid_recording_is_rejected(repo):
    ctx = fixture_run(repo)
    (repo / FX / "award.figma.json").write_text(json.dumps({"schema_version": 1, "figma_url": "x", "responses": []}))
    m = cm.run_capture(ctx, cfg())
    assert m["status"] == "failed" and m["access_failures"][0].startswith("invalid_recording")


def test_node_id_captures_only_that_frame(repo, tmp_path):
    figma_fake.build(tmp_path / "rec")
    url, transport, resolver = figma.load_recording(tmp_path / "rec/award.figma.json")
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if "/nodes" in request.url.path and "depth=1" in str(request.url):
            return httpx.Response(200, json={"nodes": {"1:3": {"document": {"id": "1:3", "name": "Packages / Details", "type": "FRAME"}}}})
        return transport.handle_request(request)
    client = figma.FigmaClient(TOKEN, cfg(), transport=httpx.MockTransport(handler), resolver=resolver,
                               sleep=lambda s: None)
    rec = cm.Recorder()
    # The recording has no nodes/images entries for a single-frame batch, so those calls 404 and the
    # frame is recorded as failed; what matters is that only 1:3 was requested.
    frames, _ = figma.capture(url + "?node-id=1-3", client, tmp_path / "capture", rec)
    assert [f["node_id"] for f in frames] == ["1:3"]
    assert all("1%3A2" not in c and "1:2" not in c for c in calls)


# --------------------------------------------------------------------------- normal mode with a token


def normal_run(repo):
    run_id = start_run(repo, url=figma_fake.URL)
    env = env_for()
    run_cli(run_state.main, script_argv(repo, "run_state", "stage", "1", "--run", run_id, "--complete"), repo, env)
    run_cli(run_state.main, script_argv(repo, "run_state", "stage", "2", "--run", run_id, "--start"), repo, env)
    return runctx.require_active_run(repo, run_id, env)


def test_normal_mode_requires_token(repo):
    ctx = normal_run(repo)
    m = cm.run_capture(ctx, cfg(), env={})
    assert m["method"] == "figma" and m["status"] == "failed"
    assert m["access_failures"][0].startswith("auth_required")


def test_token_sent_only_to_figma_api_and_never_stored(repo, tmp_path, capsys):
    figma_fake.build(tmp_path / "rec")
    _, transport, resolver = figma.load_recording(tmp_path / "rec/award.figma.json")
    seen = []

    def handler(request):
        seen.append((request.method, request.headers["host"], request.headers.get("x-figma-token")))
        return transport.handle_request(request)
    ctx = normal_run(repo)
    m = cm.run_capture(ctx, cfg(), env={"FIGMA_TOKEN": TOKEN}, transport=httpx.MockTransport(handler),
                       resolver=resolver)
    assert m["status"] == "complete"
    assert all(method == "GET" for method, _, _ in seen)
    assert all(tok == TOKEN for _, host, tok in seen if host == "api.figma.com")
    assert all(tok is None for _, host, tok in seen if host != "api.figma.com")  # not leaked to image hosts
    for f in ctx.run_dir.rglob("*"):
        if f.is_file():
            assert TOKEN.encode() not in f.read_bytes(), f
    assert TOKEN not in capsys.readouterr().out


def test_frame_image_pointing_at_internal_address_is_blocked(repo, tmp_path):
    path = figma_fake.build(tmp_path / "rec")
    data = json.loads(path.read_text())
    for r in data["responses"]:
        if "/v1/images/" in r["url"]:
            r["body_json"]["images"]["1:2"] = "http://169.254.169.254/latest/meta-data/x.png"
    path.write_text(json.dumps(data))
    _, transport, resolver = figma.load_recording(path)
    ctx = normal_run(repo)
    m = cm.run_capture(ctx, cfg(), env={"FIGMA_TOKEN": TOKEN}, transport=transport, resolver=resolver)
    f1 = m["frames"][0]
    assert f1["status"] == "captured" and f1["image"] is None and f1["node_tree"]
    assert any("FRAME-001" in x and "blocked_address" in x for x in m["limitations"])
    assert m["status"] == "partial"
    assert m["blocked_requests"][0]["page"] == "FRAME-001" and m["blocked_requests"][0]["reason"] == "blocked_address"


# --------------------------------------------------------------------------- live (opt-in)


def test_live_figma_capture(tmp_path):
    """Runs only with FIGMA_TOKEN and FRA_FIGMA_TEST_URL set; otherwise reported BLOCKED."""
    import os
    token, url = os.environ.get("FIGMA_TOKEN"), os.environ.get("FRA_FIGMA_TEST_URL")
    if not token or not url:
        pytest.skip("BLOCKED: live Figma test needs FIGMA_TOKEN and FRA_FIGMA_TEST_URL (decision f: recorded responses)")
    rec = cm.Recorder()
    frames, _ = figma.capture(url, figma.FigmaClient(token, cfg(figma_max_frames=2)), tmp_path / "capture", rec)
    assert frames and any(f["status"] == "captured" for f in frames)
    for f in (tmp_path / "capture").rglob("*"):
        if f.is_file():
            assert token.encode() not in f.read_bytes()
