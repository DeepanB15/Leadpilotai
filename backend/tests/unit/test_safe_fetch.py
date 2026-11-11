import httpx
import pytest

from app.research.safe_fetch import FetchError, SafeFetcher, UnsafeURLError, is_ip_allowed, validate_url

PUBLIC = "93.184.216.34"


def resolver_for(mapping):
    async def _r(host, port):
        return mapping.get(host, [PUBLIC])

    return _r


@pytest.mark.parametrize(
    "ip,ok",
    [
        (PUBLIC, True), ("8.8.8.8", True),
        ("127.0.0.1", False), ("10.1.2.3", False), ("172.16.0.1", False), ("192.168.1.1", False),
        ("169.254.169.254", False), ("100.64.0.1", False), ("0.0.0.0", False), ("224.0.0.1", False),
        ("::1", False), ("fe80::1", False), ("fc00::1", False), ("::ffff:127.0.0.1", False), ("::ffff:10.0.0.1", False),
        ("64:ff9b::7f00:1", False), ("2002:7f00:1::1", False), ("not-an-ip", False),
    ],
)
def test_is_ip_allowed(ip, ok):
    assert is_ip_allowed(ip) is ok


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/", "file:///etc/passwd", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/", "http://localhost/", "http://metadata.google.internal/", "http://example.com:22/",
        "http://example.com:8080/", "http://user:pw@example.com/", "http://svc.internal/", "gopher://example.com",
        "http://2130706433/",  # decimal-encoded 127.0.0.1
    ],
)
async def test_validate_url_blocks(url):
    with pytest.raises((UnsafeURLError, FetchError)):
        await validate_url(url, resolver_for({}))


async def test_validate_blocks_hostname_resolving_to_private():
    with pytest.raises(UnsafeURLError):
        await validate_url("http://evil.example.com/", resolver_for({"evil.example.com": ["10.0.0.5"]}))


async def test_validate_blocks_if_any_resolved_ip_is_private():
    with pytest.raises(UnsafeURLError):
        await validate_url("http://mixed.example.com/", resolver_for({"mixed.example.com": [PUBLIC, "127.0.0.1"]}))


async def test_validate_allows_public():
    t = await validate_url("https://example.com/a?b=1", resolver_for({}))
    assert t.port == 443 and t.path_qs == "/a?b=1" and t.ips == [PUBLIC]


def fetcher(handler, mapping=None, **kw):
    return SafeFetcher(resolver=resolver_for(mapping or {}), transport=httpx.MockTransport(handler), **kw)


async def test_fetch_pins_connection_to_validated_ip_and_sets_host():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["host"] = str(req.url), req.headers["host"]
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>ok</html>")

    res = await fetcher(handler).fetch("https://example.com/page")
    assert res.ok and "ok" in res.text
    assert PUBLIC in seen["url"] and seen["host"] == "example.com"


async def test_redirect_to_internal_address_is_blocked():
    def handler(req):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    with pytest.raises(UnsafeURLError):
        await fetcher(handler).fetch("https://example.com/")


async def test_redirect_to_hostname_resolving_internally_is_blocked():
    def handler(req):
        return httpx.Response(302, headers={"location": "https://rebind.example.net/"})

    with pytest.raises(UnsafeURLError):
        await fetcher(handler, {"rebind.example.net": ["192.168.0.10"]}).fetch("https://example.com/")


async def test_safe_redirect_is_followed():
    def handler(req):
        if req.headers["host"] == "example.com":
            return httpx.Response(301, headers={"location": "https://www.example.com/home"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>home</p>")

    res = await fetcher(handler).fetch("https://example.com/")
    assert res.final_url == "https://www.example.com/home" and res.redirects


async def test_redirect_loop_gives_up():
    def handler(req):
        return httpx.Response(302, headers={"location": "https://example.com/again"})

    with pytest.raises(FetchError):
        await fetcher(handler, max_redirects=3).fetch("https://example.com/")


async def test_response_size_is_capped():
    def handler(req):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"a" * 50_000)

    res = await fetcher(handler, max_bytes=1000).fetch("https://example.com/")
    assert res.truncated and len(res.text) <= 1000


async def test_non_html_content_type_rejected():
    def handler(req):
        return httpx.Response(200, headers={"content-type": "application/octet-stream"}, content=b"\x00\x01")

    with pytest.raises(FetchError):
        await fetcher(handler).fetch("https://example.com/file")


async def test_http_error_status_is_returned_not_raised():
    res = await fetcher(lambda r: httpx.Response(404, headers={"content-type": "text/html"}, text="nope")).fetch(
        "https://example.com/missing"
    )
    assert not res.ok and res.status_code == 404
