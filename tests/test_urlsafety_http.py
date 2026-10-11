"""SSRF protection with mocked DNS and transports; no real network (BUILD_SPEC §11.1)."""

from __future__ import annotations

import httpx
import pytest

from _lib import safe_http, urlsafety

PUBLIC = "93.184.215.14"


def resolver(table):
    def resolve(host, port):
        if host not in table:
            raise OSError(f"NXDOMAIN {host}")
        return table[host]
    return resolve


@pytest.mark.parametrize("addr", [
    "127.0.0.1", "10.1.2.3", "172.16.5.4", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
    "224.0.0.1", "255.255.255.255", "198.18.0.1", "::1", "fe80::1", "fc00::1", "fd00:ec2::254",
    "::ffff:127.0.0.1", "::ffff:169.254.169.254", "2002:7f00:1::1", "64:ff9b::a9fe:a9fe", "2001:db8::1",
])
def test_internal_addresses_are_blocked(addr):
    assert not urlsafety.address_allowed(addr)


@pytest.mark.parametrize("addr", [PUBLIC, "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(addr):
    assert urlsafety.address_allowed(addr)


@pytest.mark.parametrize("url,code", [
    ("file:///etc/passwd", "scheme_not_allowed"),
    ("ftp://example.com/", "scheme_not_allowed"),
    ("javascript:alert(1)", "scheme_not_allowed"),
    ("data:text/html,hi", "scheme_not_allowed"),
    ("gopher://example.com/", "scheme_not_allowed"),
    ("http://user:pw@example.com/", "credentials_in_url"),
    ("http://localhost/", "blocked_hostname"),
    ("http://metadata.google.internal/", "blocked_hostname"),
    ("http://printer.local/", "blocked_hostname"),
    ("http://169.254.169.254/latest/meta-data/", "blocked_address"),
    ("http://[::1]/", "blocked_address"),
    ("http://unknown.example/", "dns_failure"),
    ("http://rebind.example/", "blocked_address"),
    ("http://mixed.example/", "blocked_address"),
    ("http:///nohost", "missing_host"),
    ("http://exa\nmple.com/", "invalid_url"),
])
def test_validate_url_blocks(url, code):
    r = resolver({"rebind.example": ["10.0.0.7"], "mixed.example": [PUBLIC, "127.0.0.1"]})
    with pytest.raises(urlsafety.UrlBlocked) as exc:
        urlsafety.validate_url(url, resolver=r)
    assert exc.value.code == code


def test_decimal_ip_host_is_resolved_and_blocked():
    # urlsplit keeps "2130706433"; the resolver turns it into 127.0.0.1, which is rejected.
    with pytest.raises(urlsafety.UrlBlocked):
        urlsafety.validate_url("http://2130706433/", resolver=lambda h, p: ["127.0.0.1"])


def test_config_cannot_add_schemes():
    with pytest.raises(urlsafety.UrlBlocked):
        urlsafety.validate_url("file:///x", allowed_schemes=("http", "https", "file"))


def test_extra_blocked_hostnames():
    with pytest.raises(urlsafety.UrlBlocked):
        urlsafety.validate_url("https://a.corp.example/", blocked_hostnames=("corp.example",),
                               resolver=resolver({"a.corp.example": [PUBLIC]}))


def test_resolution_error_fails_closed():
    def broken(host, port):
        raise OSError("resolver down")
    with pytest.raises(urlsafety.UrlBlocked) as exc:
        urlsafety.validate_url("https://example.com/", resolver=broken)
    assert exc.value.code == "dns_failure"


# --------------------------------------------------------------------------- safe_http


def policy(**kw):
    return safe_http.HttpPolicy(**kw)


def test_connects_to_validated_ip_with_host_header_and_sni():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["host"] = request.headers["host"]
        seen["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<p>ok</p>")

    res = safe_http.fetch("https://mockup.example.com/page?x=1", policy(),
                          resolver=resolver({"mockup.example.com": [PUBLIC]}),
                          transport=httpx.MockTransport(handler))
    assert res.status == 200 and res.body == b"<p>ok</p>"
    assert seen["url"] == f"https://{PUBLIC}/page?x=1"
    assert seen["host"] == "mockup.example.com"
    assert seen["sni"] == "mockup.example.com"


def test_public_url_redirecting_to_internal_is_blocked():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    with pytest.raises(safe_http.FetchBlocked) as exc:
        safe_http.fetch("https://public.example/", policy(), resolver=resolver({"public.example": [PUBLIC]}),
                        transport=httpx.MockTransport(handler))
    assert exc.value.code == "blocked_address"
    assert "169.254.169.254" in exc.value.url


def test_redirect_to_hostname_resolving_private_is_blocked():
    def handler(request):
        return httpx.Response(301, headers={"location": "https://intranet.example/"})

    with pytest.raises(safe_http.FetchBlocked) as exc:
        safe_http.fetch("https://public.example/", policy(),
                        resolver=resolver({"public.example": [PUBLIC], "intranet.example": ["192.168.0.10"]}),
                        transport=httpx.MockTransport(handler))
    assert exc.value.code == "blocked_address"


def test_redirect_limit():
    def handler(request):
        return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(safe_http.FetchBlocked) as exc:
        safe_http.fetch("https://public.example/", policy(max_redirects=3),
                        resolver=resolver({"public.example": [PUBLIC]}), transport=httpx.MockTransport(handler))
    assert exc.value.code == "too_many_redirects"


def test_byte_limit_while_streaming():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 5000)

    with pytest.raises(safe_http.FetchBlocked) as exc:
        safe_http.fetch("https://public.example/", policy(max_bytes=1000),
                        resolver=resolver({"public.example": [PUBLIC]}), transport=httpx.MockTransport(handler))
    assert exc.value.code == "too_large"


def test_content_type_allow_list():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/x-msdownload"}, content=b"MZ")

    with pytest.raises(safe_http.FetchBlocked) as exc:
        safe_http.fetch("https://public.example/", policy(allowed_content_types=("image/png",)),
                        resolver=resolver({"public.example": [PUBLIC]}), transport=httpx.MockTransport(handler))
    assert exc.value.code == "content_type_not_allowed"


def test_only_get_and_head():
    with pytest.raises(safe_http.FetchBlocked) as exc:
        safe_http.fetch("https://public.example/", policy(), method="POST",
                        resolver=resolver({"public.example": [PUBLIC]}))
    assert exc.value.code == "method_not_allowed"


def test_redirect_returned_unfollowed_for_browser():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://10.0.0.1/"})

    res = safe_http.fetch("https://public.example/", policy(), follow_redirects=False,
                          resolver=resolver({"public.example": [PUBLIC]}), transport=httpx.MockTransport(handler))
    assert res.status == 302  # the browser's next request for 10.0.0.1 is validated (and blocked) separately
