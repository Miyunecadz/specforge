"""HTTP client with SSRF protections (BUILD_SPEC §11.1). Requires httpx.

- Every URL, including every redirect target, goes through urlsafety.validate_url().
- Connections go to the validated IP address; the hostname is sent as Host and as TLS SNI,
  and the certificate is verified against the hostname (DNS-rebinding mitigation).
- Connect/read timeouts per request, a total deadline, a redirect limit, a byte limit
  enforced while streaming, and an optional content-type allow list.
- Environment proxies are ignored. Only GET and HEAD are ever sent.
"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from . import urlsafety


class FetchBlocked(Exception):
    def __init__(self, code: str, detail: str = "", url: str | None = None):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.url = url


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    headers: dict
    body: bytes
    content_type: str
    redirects: list[str] = field(default_factory=list)


@dataclass
class HttpPolicy:
    allowed_schemes: tuple[str, ...] = ("http", "https")
    blocked_hostnames: tuple[str, ...] = ()
    max_redirects: int = 5
    connect_timeout: float = 10.0
    read_timeout: float = 20.0
    total_timeout: float = 60.0
    max_bytes: int = 10 * 1024 * 1024
    allowed_content_types: tuple[str, ...] | None = None

    @classmethod
    def from_config(cls, config: dict, max_bytes: int, content_types=None) -> "HttpPolicy":
        net = config["network"]
        return cls(
            allowed_schemes=tuple(net["allowed_schemes"]),
            blocked_hostnames=tuple(net["blocked_hostnames"]),
            max_redirects=net["max_redirects"],
            connect_timeout=net["connect_timeout_s"],
            read_timeout=net["read_timeout_s"],
            total_timeout=net["total_timeout_s"],
            max_bytes=max_bytes,
            allowed_content_types=tuple(content_types) if content_types else None,
        )


def _pinned_url(v: urlsafety.ValidatedUrl, address: str) -> str:
    parts = urlsplit(v.url)
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    host = f"[{ip}]" if ip.version == 6 else str(ip)
    netloc = host if v.port == urlsafety.DEFAULT_PORTS[v.scheme] else f"{host}:{v.port}"
    return urlunsplit((v.scheme, netloc, parts.path or "/", parts.query, ""))


def _host_header(v: urlsafety.ValidatedUrl) -> str:
    return v.host if v.port == urlsafety.DEFAULT_PORTS[v.scheme] else f"{v.host}:{v.port}"


def _media_type(ct: str) -> str:
    return ct.split(";", 1)[0].strip().lower()


def fetch(
    url: str,
    policy: HttpPolicy,
    *,
    resolver: urlsafety.Resolver = urlsafety.system_resolver,
    transport: httpx.BaseTransport | None = None,
    follow_redirects: bool = True,
    method: str = "GET",
    headers: dict | None = None,
) -> FetchResult:
    if method not in ("GET", "HEAD"):
        raise FetchBlocked("method_not_allowed", method, url)
    deadline = time.monotonic() + policy.total_timeout
    redirects: list[str] = []
    current = url
    timeout = httpx.Timeout(policy.connect_timeout, read=policy.read_timeout, write=policy.read_timeout,
                            pool=policy.connect_timeout)
    with httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=timeout,
                      verify=True) as client:
        while True:
            try:
                v = urlsafety.validate_url(current, allowed_schemes=policy.allowed_schemes,
                                           blocked_hostnames=policy.blocked_hostnames, resolver=resolver)
            except urlsafety.UrlBlocked as exc:
                raise FetchBlocked(exc.code, exc.detail, current) from exc
            req_headers = {"Host": _host_header(v), "User-Agent": "feature-research-agent/0.1",
                           "Accept-Encoding": "gzip, deflate"}
            req_headers.update(headers or {})
            request = client.build_request(method, _pinned_url(v, v.addresses[0]), headers=req_headers,
                                           extensions={"sni_hostname": v.host})
            try:
                resp = client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                raise FetchBlocked("timeout", str(exc), current) from exc
            except httpx.HTTPError as exc:
                raise FetchBlocked("connection_failed", str(exc), current) from exc
            try:
                if resp.is_redirect and follow_redirects:
                    location = resp.headers.get("location", "")
                    if len(redirects) >= policy.max_redirects:
                        raise FetchBlocked("too_many_redirects", str(policy.max_redirects), current)
                    nxt = urljoin(current, location)
                    redirects.append(nxt)
                    current = nxt
                    continue
                ctype = resp.headers.get("content-type", "")
                if (policy.allowed_content_types and not resp.is_redirect and resp.status_code < 400
                        and _media_type(ctype) not in policy.allowed_content_types):
                    raise FetchBlocked("content_type_not_allowed", _media_type(ctype) or "(none)", current)
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > policy.max_bytes:
                    raise FetchBlocked("too_large", f"content-length {declared} > {policy.max_bytes}", current)
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > policy.max_bytes:
                        raise FetchBlocked("too_large", f"more than {policy.max_bytes} bytes", current)
                    if time.monotonic() > deadline:
                        raise FetchBlocked("timeout", "total timeout exceeded", current)
                    chunks.append(chunk)
                return FetchResult(
                    url=url, final_url=current, status=resp.status_code,
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    body=b"".join(chunks), content_type=_media_type(ctype), redirects=redirects,
                )
            except httpx.TimeoutException as exc:
                raise FetchBlocked("timeout", str(exc), current) from exc
            except httpx.HTTPError as exc:
                raise FetchBlocked("connection_failed", str(exc), current) from exc
            finally:
                resp.close()
