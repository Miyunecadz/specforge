#!/usr/bin/env python3
"""check_url.py --run <run-id> <url>: validate a mockup URL before capture (BUILD_SPEC §10).

Normal mode: syntax and scheme, destination resolution against internal ranges (§11.1),
redirects and final destination, reachability, content type, and likely authentication
requirements. Fixture mode: the target must be a file inside the fixture directory; no
network access. Prints structured JSON; writes nothing. Exit 0 when status is "ok".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import fixtures, modes, paths, runctx, safe_http, urlsafety  # noqa: E402
from _lib.runctx import RunError  # noqa: E402

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
FIGMA_HOSTS = ("figma.com", "www.figma.com")


def is_figma(url: str) -> bool:
    parts = urlsplit(url)
    return (parts.hostname or "").lower() in FIGMA_HOSTS and parts.path.split("/")[1:2] in (
        ["file"], ["design"], ["proto"], ["board"])


def check(url: str, mode: modes.Mode, config: dict, env: Mapping[str, str], *, resolver=None,
          transport=None) -> dict:
    result = {"status": "ok", "reason": None, "input_type": None, "final_url": None,
              "http_status": None, "content_type": None, "auth_required": False, "warnings": []}
    if mode.mode == modes.FIXTURE:
        try:
            target = fixtures.resolve_target(url, mode.fixture_dir)
        except fixtures.FixtureError as exc:
            return {**result, "status": "blocked", "reason": f"fixture_target: {exc}"}
        result["final_url"] = target.relative_to(mode.fixture_dir.resolve()).as_posix()
        suffix = target.suffix.lower()
        if target.name.lower().endswith(".figma.json"):
            result["input_type"] = "figma"  # recorded Figma responses, replayed offline
            return result
        result["input_type"] = "image" if suffix in IMAGE_SUFFIXES else "html" if suffix in (".html", ".htm") else None
        if result["input_type"] is None:
            return {**result, "status": "unsupported", "reason": f"unsupported fixture type {suffix}"}
        return result

    net = config["network"]
    try:
        urlsafety.validate_url(url, allowed_schemes=net["allowed_schemes"],
                               blocked_hostnames=net["blocked_hostnames"],
                               resolver=resolver or urlsafety.system_resolver)
    except urlsafety.UrlBlocked as exc:
        return {**result, "status": "blocked", "reason": exc.code, "warnings": [exc.detail] if exc.detail else []}

    if is_figma(url):
        result["input_type"] = "figma"
        if "figma" not in config["capture"]["supported_methods"]:
            return {**result, "status": "unsupported", "reason": "figma capture disabled in config"}
        if not env.get("FIGMA_TOKEN"):
            return {**result, "status": "auth_required", "auth_required": True,
                    "reason": "FIGMA_TOKEN is not set. Create a Figma personal access token with read-only "
                              "file-content scope and export it as FIGMA_TOKEN, then retry."}
        return result

    policy = safe_http.HttpPolicy.from_config(config, max_bytes=config["capture"]["max_bytes_per_resource"])
    try:
        res = safe_http.fetch(url, policy, resolver=resolver or urlsafety.system_resolver, transport=transport)
    except safe_http.FetchBlocked as exc:
        blocked = exc.code in ("scheme_not_allowed", "blocked_address", "blocked_hostname",
                               "credentials_in_url", "invalid_url", "missing_host", "too_many_redirects")
        return {**result, "status": "blocked" if blocked else "unreachable", "reason": exc.code,
                "final_url": exc.url, "warnings": [exc.detail] if exc.detail else []}
    result.update(final_url=res.final_url, http_status=res.status, content_type=res.content_type)
    if res.redirects:
        result["warnings"].append(f"followed {len(res.redirects)} redirect(s)")
    if res.status in (401, 403, 407):
        return {**result, "status": "auth_required", "auth_required": True,
                "reason": f"HTTP {res.status}: the mockup appears to require authentication; "
                          "share a public link or provide access. Authentication is never bypassed."}
    if res.status >= 400:
        return {**result, "status": "unreachable", "reason": f"HTTP {res.status}"}
    if res.content_type in config["capture"]["image_content_types"]:
        result["input_type"] = "image"
    elif res.content_type in ("text/html", "application/xhtml+xml"):
        result["input_type"] = "html"
        low = res.body[:200000].decode("utf-8", "replace").lower()
        if 'type="password"' in low or "type='password'" in low:
            result["auth_required"] = True
            result["warnings"].append("the page contains a password field; it may be a login page")
    else:
        return {**result, "status": "unsupported", "reason": f"unsupported content type {res.content_type!r}"}
    if result["input_type"] not in config["capture"]["supported_methods"]:
        return {**result, "status": "unsupported", "reason": f"{result['input_type']} capture disabled in config"}
    return result


def main(argv: Sequence[str] | None = None, repo: Path | None = None,
         env: Mapping[str, str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("url")
    args = ap.parse_args(None if argv is None else list(argv)[1:])
    repo = repo or paths.REPO_ROOT
    env = os.environ if env is None else env
    try:
        ctx = runctx.require_active_run(repo, args.run, env)
        config = runctx.load_config(repo)
    except RunError as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}))
        return 3
    result = check(args.url, ctx.mode, config, env)
    result["mode"] = ctx.mode.mode
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
