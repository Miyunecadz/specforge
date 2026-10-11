"""Figma capture through the REST API (BUILD_SPEC §4 Figma, §7 Stage 2). Requires httpx.

- Read-only: only GET requests are sent (safe_http refuses anything else), with the
  personal access token from FIGMA_TOKEN in the X-Figma-Token header. The token is never
  written to any file, log or error message.
- Rate limiting: on HTTP 429 the client waits for Retry-After (or exponential back-off from
  figma_backoff_base_s) and retries at most figma_max_retries times; exhausted retries are a
  capture failure.
- Large files: at most figma_max_frames frames are captured. With a node-id in the URL only
  that node (or its child frames) is captured. Skipped frames make the capture partial.
- Every request, including the frame-image downloads Figma redirects to, goes through
  safe_http's SSRF checks.
- Fixture mode replays a recording (`*.figma.json`) through the same code path with no
  network access at all.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from . import fsutil, safe_http, urlsafety

API = "https://api.figma.com"
URL_RE = re.compile(r"^/(file|design|proto|board)/([A-Za-z0-9]{10,64})(/|$)")
FRAME_TYPES = {"FRAME", "COMPONENT", "COMPONENT_SET", "SECTION"}
KEEP_FIELDS = ("id", "name", "type", "characters", "componentId", "visible", "absoluteBoundingBox")
NODE_BATCH = 5
MAX_RETRY_AFTER_S = 120


class FigmaError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass
class FigmaTarget:
    file_key: str
    node_id: str | None


def parse_url(url: str) -> FigmaTarget:
    parts = urlsplit(url)
    if (parts.hostname or "").lower() not in ("figma.com", "www.figma.com"):
        raise FigmaError("not_figma", "not a figma.com URL")
    m = URL_RE.match(parts.path)
    if not m:
        raise FigmaError("invalid_figma_url", "expected /file|design|proto|board/<file-key>/...")
    node = parse_qs(parts.query).get("node-id", [None])[0]
    if node is not None:
        node = node.replace("-", ":")
        if not re.fullmatch(r"[0-9]+:[0-9]+", node):
            raise FigmaError("invalid_node_id", node)
    return FigmaTarget(m.group(2), node)


# --------------------------------------------------------------------------- recordings


def load_recording(path: Path) -> tuple[str, httpx.MockTransport, Callable]:
    """Return (figma URL, transport, resolver) replaying a recording; no network access.

    Recording format (schemas/figma_recording.schema.json):
      {"schema_version": 1, "figma_url": "...", "responses": [
         {"url": "https://api.figma.com/v1/...", "status": 200, "headers": {...},
          "body_json": {...}} | {..., "body_file": "frame-1.png"}]}
    Responses for the same URL are served in order (e.g. a 429 followed by a 200).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    queues: dict[str, list[dict]] = {}
    for r in data["responses"]:
        queues.setdefault(_key(r["url"]), []).append(r)
    base = path.parent.resolve()

    def handler(request: httpx.Request) -> httpx.Response:
        url = f"https://{request.headers['host']}{request.url.raw_path.decode()}"
        queue = queues.get(_key(url))
        if not queue:
            return httpx.Response(404, json={"status": 404, "err": "not in recording"})
        r = queue.pop(0) if len(queue) > 1 else queue[0]
        headers = dict(r.get("headers", {}))
        if "body_file" in r:
            f = (base / r["body_file"]).resolve()
            if base not in f.parents or not f.is_file():
                return httpx.Response(404)
            return httpx.Response(r["status"], headers=headers, content=f.read_bytes())
        headers.setdefault("content-type", "application/json")
        return httpx.Response(r["status"], headers=headers, content=json.dumps(r.get("body_json", {})).encode())

    return data["figma_url"], httpx.MockTransport(handler), (lambda host, port: ["93.184.215.14"])


def _key(url: str) -> str:
    p = urlsplit(url)
    q = urlencode(sorted(parse_qs(p.query).items()), doseq=True)
    return f"{(p.hostname or '').lower()}{p.path}?{q}"


# --------------------------------------------------------------------------- client


@dataclass
class FigmaClient:
    token: str
    config: dict
    transport: httpx.BaseTransport | None = None
    resolver: Callable = urlsafety.system_resolver
    sleep: Callable[[float], None] = time.sleep
    warnings: list = field(default_factory=list)

    def _policy(self, content_types):
        return safe_http.HttpPolicy.from_config(self.config, self.config["capture"]["max_bytes_per_resource"],
                                                content_types)

    def get_json(self, path: str, params: dict | None = None) -> dict:
        url = API + path + ("?" + urlencode(params) if params else "")
        cap = self.config["capture"]
        for attempt in range(cap["figma_max_retries"] + 1):
            try:
                res = safe_http.fetch(url, self._policy(None), resolver=self.resolver, transport=self.transport,
                                      headers={"X-Figma-Token": self.token})
            except safe_http.FetchBlocked as exc:
                raise FigmaError(exc.code, self._scrub(exc.detail)) from exc
            if res.status == 429:
                if attempt >= cap["figma_max_retries"]:
                    raise FigmaError("rate_limited", f"HTTP 429 after {cap['figma_max_retries']} retries ({path})")
                wait = _retry_after(res.headers.get("retry-after"))
                if wait is None:
                    wait = cap["figma_backoff_base_s"] * (2 ** attempt)
                if wait > MAX_RETRY_AFTER_S:
                    raise FigmaError("rate_limited", f"Retry-After {wait:.0f}s exceeds {MAX_RETRY_AFTER_S}s ({path})")
                self.warnings.append(f"Figma rate limit (HTTP 429) on {path}; waited {wait:.1f}s before retry "
                                     f"{attempt + 1}/{cap['figma_max_retries']}")
                self.sleep(wait)
                continue
            if res.status in (401, 403):
                raise FigmaError("access_denied", f"HTTP {res.status}: the token cannot read this file "
                                                  "(needs read-only file-content access)")
            if res.status == 404:
                raise FigmaError("not_found", f"HTTP 404 for {path}")
            if res.status >= 400:
                raise FigmaError("http_error", f"HTTP {res.status} for {path}")
            try:
                return json.loads(res.body)
            except ValueError as exc:
                raise FigmaError("invalid_json", path) from exc
        raise FigmaError("rate_limited", path)  # unreachable

    def download_image(self, url: str) -> tuple[bytes, str]:
        try:
            res = safe_http.fetch(url, self._policy(self.config["capture"]["image_content_types"]),
                                  resolver=self.resolver, transport=self.transport)
        except safe_http.FetchBlocked as exc:
            raise FigmaError(exc.code, self._scrub(exc.detail)) from exc
        if res.status >= 400:
            raise FigmaError("http_error", f"HTTP {res.status} for frame image")
        return res.body, res.content_type

    def _scrub(self, text: str) -> str:
        return text.replace(self.token, "[token]") if self.token else text


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


# --------------------------------------------------------------------------- capture


def trim(node: dict, frame_ids: dict[str, str], links: list, frame_id: str) -> dict:
    out = {k: node[k] for k in KEEP_FIELDS if k in node}
    dests = set()
    if node.get("transitionNodeID"):
        dests.add(node["transitionNodeID"])
    for reaction in node.get("reactions") or []:
        for action in ([reaction.get("action")] if reaction.get("action") else []) + (reaction.get("actions") or []):
            if action and action.get("destinationId"):
                dests.add(action["destinationId"])
    for d in sorted(dests):
        links.append({"from": frame_id, "href": f"figma-node:{d}", "text": node.get("name", ""),
                      "same_origin": True, "followed": False, "_dest": d})
    if node.get("children"):
        out["children"] = [trim(c, frame_ids, links, frame_id) for c in node["children"]]
    return out


def text_layers(node: dict, out: list) -> list:
    if node.get("type") == "TEXT" and node.get("characters"):
        out.append(f"{node.get('name', '')}: {node['characters']}")
    for c in node.get("children") or []:
        text_layers(c, out)
    return out


def capture(url: str, client: FigmaClient, cap_dir: Path, rec) -> tuple[list, list]:
    """Capture frames into cap_dir. Returns (frames, links). Raises FigmaError on access failure."""
    target = parse_url(url)
    max_frames = client.config["capture"]["figma_max_frames"]
    candidates: list[tuple[str, str, str | None]] = []  # (node id, name, page name)
    if target.node_id:
        data = client.get_json(f"/v1/files/{target.file_key}/nodes", {"ids": target.node_id, "depth": 1})
        doc = ((data.get("nodes") or {}).get(target.node_id) or {}).get("document")
        if not doc:
            raise FigmaError("not_found", f"node {target.node_id} not in file")
        if doc.get("type") in FRAME_TYPES:
            candidates.append((doc["id"], doc.get("name", ""), None))
        else:
            candidates += [(c["id"], c.get("name", ""), doc.get("name")) for c in doc.get("children") or []
                           if c.get("type") in FRAME_TYPES]
    else:
        data = client.get_json(f"/v1/files/{target.file_key}", {"depth": 2})
        for page in (data.get("document") or {}).get("children") or []:
            for c in page.get("children") or []:
                if c.get("type") in FRAME_TYPES:
                    candidates.append((c["id"], c.get("name", ""), page.get("name")))
    if not candidates:
        raise FigmaError("no_frames", "no top-level frames found")

    frames: list[dict] = []
    for i, (node_id, name, page_name) in enumerate(candidates, start=1):
        frames.append({"id": f"FRAME-{i:03d}", "name": name, "node_id": node_id, "page_name": page_name,
                       "status": "skipped" if i > max_frames else "captured", "image": None,
                       "node_tree": None, "text": None,
                       "error": f"frame limit figma_max_frames={max_frames} reached" if i > max_frames else None})
    selected = [f for f in frames if f["status"] == "captured"]
    by_node = {f["node_id"]: f["id"] for f in frames}
    (cap_dir / "frames").mkdir(parents=True, exist_ok=True)
    (cap_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    links: list = []

    for start in range(0, len(selected), NODE_BATCH):
        batch = selected[start:start + NODE_BATCH]
        try:
            data = client.get_json(f"/v1/files/{target.file_key}/nodes", {"ids": ",".join(f["node_id"] for f in batch)})
        except FigmaError as exc:
            if exc.code in ("rate_limited", "access_denied"):
                raise
            for f in batch:
                f.update(status="failed", error=f"node tree: {exc}")
            continue
        for f in batch:
            doc = ((data.get("nodes") or {}).get(f["node_id"]) or {}).get("document")
            if not doc:
                f.update(status="failed", error="node not returned by the API")
                continue
            stem = f["id"].lower()
            tree = trim(doc, by_node, links, f["id"])
            fsutil.atomic_write_json(cap_dir / "frames" / f"{stem}.json", tree)
            f["node_tree"] = f"capture/frames/{stem}.json"
            (cap_dir / "frames" / f"{stem}.txt").write_text("\n".join(text_layers(doc, [])) + "\n", encoding="utf-8")
            f["text"] = f"capture/frames/{stem}.txt"

    ok = [f for f in selected if f["status"] == "captured"]
    if ok:
        try:
            data = client.get_json(f"/v1/images/{target.file_key}",
                                   {"ids": ",".join(f["node_id"] for f in ok), "format": "png", "scale": 1})
            images = data.get("images") or {}
        except FigmaError as exc:
            if exc.code in ("rate_limited", "access_denied"):
                raise
            images = {}
            rec.warnings.append(f"frame images unavailable: {exc}")
        for f in ok:
            src = images.get(f["node_id"])
            if not src:
                rec.limitations.append(f"{f['id']} ({f['name']}): no rendered image returned; node tree only")
                continue
            try:
                body, _ = client.download_image(src)
            except FigmaError as exc:
                rec.limitations.append(f"{f['id']} ({f['name']}): image download failed ({exc.code})")
                policy = exc.code in ("blocked_address", "blocked_hostname", "scheme_not_allowed",
                                      "credentials_in_url", "dns_failure", "invalid_url", "missing_host")
                (rec.block if policy else rec.fail)(src, f["id"], "image", exc.code)
                continue
            rec.bytes_total += len(body)
            path = cap_dir / "screenshots" / f"{f['id'].lower()}.png"
            fsutil.atomic_write_bytes(path, body)
            f["image"] = f"capture/screenshots/{f['id'].lower()}.png"

    for link in links:
        dest = link.pop("_dest")
        link["to"] = by_node.get(dest)
        link["followed"] = link["to"] is not None and next(f for f in frames if f["id"] == link["to"])["status"] == "captured"
    skipped = [f for f in frames if f["status"] == "skipped"]
    if skipped:
        rec.limitations.append(f"{len(skipped)} of {len(frames)} frames were not captured because figma_max_frames="
                               f"{max_frames}; the capture is partial.")
    rec.warnings.extend(client.warnings)
    return frames, links
