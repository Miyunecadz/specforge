"""Fixture-mode target resolution (BUILD_SPEC §16). Stdlib only.

In fixture mode a mockup "URL" is a path inside the fixture directory: an absolute path,
a path relative to the fixture directory, or a file:// URL. Fixture pages are served to
the browser from the reserved origin http://fixture.invalid/ by the capture route handler,
so every request is intercepted and nothing reaches the network.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

FIXTURE_ORIGIN = "http://fixture.invalid"
FIXTURE_HOST = "fixture.invalid"


class FixtureError(ValueError):
    pass


def resolve_target(url: str, fixture_dir: Path) -> Path:
    root = fixture_dir.resolve()
    if url.startswith("file://"):
        parts = urlsplit(url)
        if parts.netloc not in ("", "localhost"):
            raise FixtureError("file:// URLs must not name a host")
        raw = Path(unquote(parts.path))
    elif "://" in url:
        raise FixtureError("fixture mode accepts only fixture paths or file:// URLs; no network URLs")
    else:
        raw = Path(url)
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise FixtureError(f"{url!r} is outside the fixture directory")
    if not resolved.is_file():
        raise FixtureError(f"fixture file not found: {url!r}")
    return resolved


def to_fixture_url(path: Path, fixture_dir: Path) -> str:
    rel = path.resolve().relative_to(fixture_dir.resolve()).as_posix()
    return f"{FIXTURE_ORIGIN}/{rel}"


def from_fixture_url(url: str, fixture_dir: Path) -> Path | None:
    """Map a request URL back to a fixture file; None if not a fixture-origin URL or outside."""
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname != FIXTURE_HOST or parts.port is not None:
        return None
    root = fixture_dir.resolve()
    rel = unquote(parts.path).lstrip("/") or "index.html"
    resolved = (root / rel).resolve()
    if resolved != root and root not in resolved.parents:
        return None
    if resolved.is_dir():
        resolved = resolved / "index.html"
    return resolved
