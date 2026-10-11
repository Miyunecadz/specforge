"""URL and SSRF protection (BUILD_SPEC §11.1). Stdlib only.

validate_url() allows only http/https, rejects credentials in URLs, resolves the host and
rejects the URL if ANY resolved address is loopback, private, link-local, shared, reserved,
multicast, documentation, or a cloud metadata address (including IPv4-mapped, 6to4,
Teredo and NAT64 forms). Resolution failure fails closed. The returned addresses are what
the HTTP client must connect to (DNS-rebinding mitigation).
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urlsplit

Resolver = Callable[[str, int], list[str]]

_BLOCKED_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
        "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
        "255.255.255.255/32",
        "::/128", "::1/128", "100::/64", "2001:db8::/32", "fc00::/7", "fe80::/10",
        "fec0::/10", "ff00::/8",
    )
]
_NAT64 = [ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48")]
_BLOCKED_NAMES = ("localhost", "metadata.google.internal", "metadata", "instance-data")
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa")
DEFAULT_PORTS = {"http": 80, "https": 443}


class UrlBlocked(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ValidatedUrl:
    url: str
    scheme: str
    host: str  # IDNA-encoded hostname, or the IP literal
    port: int
    addresses: tuple[str, ...]


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def _embedded_v4(ip: ipaddress.IPv6Address) -> Iterable[ipaddress.IPv4Address]:
    if ip.ipv4_mapped:
        yield ip.ipv4_mapped
    if ip.sixtofour:
        yield ip.sixtofour
    if ip.teredo:
        yield from ip.teredo
    for net in _NAT64:
        if ip in net:
            yield ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)


def address_allowed(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        for v4 in _embedded_v4(ip):
            if not address_allowed(str(v4)):
                return False
        if ip.ipv4_mapped:
            return True  # judged by the embedded IPv4 address above
    if any(ip in net for net in _BLOCKED_NETS):
        return False
    return ip.is_global


def host_name_blocked(host: str, extra: Iterable[str] = ()) -> bool:
    h = host.lower().rstrip(".")
    if h in _BLOCKED_NAMES or h.endswith(_BLOCKED_SUFFIXES):
        return True
    for name in extra:
        name = name.lower().rstrip(".")
        if h == name or h.endswith("." + name):
            return True
    return False


def validate_url(
    url: str,
    *,
    allowed_schemes: Iterable[str] = ("http", "https"),
    blocked_hostnames: Iterable[str] = (),
    resolver: Resolver = system_resolver,
) -> ValidatedUrl:
    if not isinstance(url, str) or not url or any(c in url for c in "\r\n\t\x00"):
        raise UrlBlocked("invalid_url", "empty or contains control characters")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UrlBlocked("invalid_url", str(exc)) from exc
    scheme = parts.scheme.lower()
    allowed = {s for s in allowed_schemes if s in ("http", "https")}
    if scheme not in allowed:
        raise UrlBlocked("scheme_not_allowed", scheme or "(none)")
    if parts.username is not None or parts.password is not None:
        raise UrlBlocked("credentials_in_url")
    host = parts.hostname
    if not host:
        raise UrlBlocked("missing_host")
    try:
        ip_literal = ipaddress.ip_address(host)
    except ValueError:
        ip_literal = None
    if ip_literal is None:
        try:
            host = host.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise UrlBlocked("invalid_host", str(exc)) from exc
        if host_name_blocked(host, blocked_hostnames):
            raise UrlBlocked("blocked_hostname", host)
    port = port or DEFAULT_PORTS[scheme]
    if ip_literal is not None:
        addresses = [str(ip_literal)]
    else:
        try:
            addresses = resolver(host, port)
        except (OSError, UnicodeError) as exc:
            raise UrlBlocked("dns_failure", f"{host}: {exc}") from exc
        if not addresses:
            raise UrlBlocked("dns_failure", f"{host}: no addresses")
    bad = [a for a in addresses if not address_allowed(a)]
    if bad:
        raise UrlBlocked("blocked_address", f"{host} resolves to non-public address {bad[0]}")
    return ValidatedUrl(url, scheme, host, port, tuple(addresses))
