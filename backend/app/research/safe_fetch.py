"""SSRF-hardened HTTP fetcher.

Every outbound request to a user-influenced URL must go through ``SafeFetcher``:
  * http/https only, ports 80/443 only, no credentials in the URL
  * hostnames resolved and *every* resolved address must be globally routable
    (blocks loopback, private, link-local incl. cloud metadata 169.254.169.254, CGNAT, reserved, multicast)
  * the connection is pinned to the validated IP (defeats DNS rebinding); TLS SNI/cert
    verification still uses the original hostname
  * redirects are followed manually and each hop is re-validated
  * timeouts, decoded-size cap, content-type allowlist, per-domain rate limiting
"""

import asyncio
import ipaddress
import re
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

ALLOWED_PORTS = {80, 443}
BLOCKED_HOSTNAMES = {"metadata.google.internal", "metadata", "instance-data", "localhost"}
BLOCKED_SUFFIXES = (".internal", ".local", ".localhost", ".lan", ".home.arpa")
HTML_TYPES = ("text/html", "application/xhtml+xml")
TEXT_TYPES = ("text/plain",)

_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class UnsafeURLError(Exception):
    """The URL (or a redirect/DNS result) is not allowed to be fetched."""


class FetchError(Exception):
    """Network-level failure (timeout, connection error, too many redirects, bad content type...)."""

    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.transient = transient


def is_ip_allowed(ip: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    try:
        addr = ipaddress.ip_address(ip) if isinstance(ip, str) else ip
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        elif addr in _NAT64:
            addr = ipaddress.IPv4Address(addr.packed[-4:])
        elif addr.sixtofour:
            addr = addr.sixtofour
    return addr.is_global and not addr.is_multicast


Resolver = Callable[[str, int], Awaitable[list[str]]]


async def default_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"DNS resolution failed for {host}", transient=True) from exc
    return list(dict.fromkeys(i[4][0] for i in infos))


@dataclass
class Target:
    url: str
    scheme: str
    host: str
    port: int
    path_qs: str
    ips: list[str]


async def validate_url(url: str, resolver: Resolver = default_resolver) -> Target:
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError as exc:
        raise UnsafeURLError("Malformed URL") from exc
    if p.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http and https are allowed")
    if p.username or p.password:
        raise UnsafeURLError("Credentials in URL are not allowed")
    host = (p.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeURLError("Missing hostname")
    port = port or (443 if p.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise UnsafeURLError(f"Port {port} is not allowed")
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
        raise UnsafeURLError("Hostname is not allowed")

    # IP literal?
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is None and re.fullmatch(r"0x[0-9a-f]+|\d+", host.split(".")[-1]):
        # inet_aton-style encodings (2130706433, 0x7f.1, 017700000001) are IPs in disguise
        raise UnsafeURLError("Numeric hostnames are not allowed")
    if literal is not None:
        if not is_ip_allowed(literal):
            raise UnsafeURLError("Address is not publicly routable")
        ips = [str(literal)]
    else:
        ips = await resolver(host, port)
        if not ips:
            raise FetchError(f"No addresses for {host}", transient=True)
        bad = [ip for ip in ips if "%" in ip or not is_ip_allowed(ip)]
        if bad:
            raise UnsafeURLError("Hostname resolves to a non-public address")

    path_qs = p.path or "/"
    if p.query:
        path_qs += "?" + p.query
    return Target(url=url, scheme=p.scheme, host=host, port=port, path_qs=path_qs, ips=ips)


class DomainRateLimiter:
    """Minimum interval between requests to the same host."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}

    async def wait(self, host: str) -> None:
        if self.min_interval <= 0:
            return
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            delay = self._last.get(host, 0.0) + self.min_interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last[host] = time.monotonic()


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content_type: str
    text: str
    truncated: bool = False
    redirects: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


def _ip_netloc(ip: str, port: int, scheme: str) -> str:
    host = f"[{ip}]" if ":" in ip else ip
    default = 443 if scheme == "https" else 80
    return host if port == default else f"{host}:{port}"


class SafeFetcher:
    def __init__(
        self,
        *,
        timeout: float = 12.0,
        max_bytes: int = 2_000_000,
        max_redirects: int = 5,
        user_agent: str = "LeadPilotAI-Research/1.0",
        resolver: Resolver = default_resolver,
        transport: httpx.AsyncBaseTransport | None = None,
        rate_limiter: DomainRateLimiter | None = None,
    ):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self.resolver = resolver
        self.rate_limiter = rate_limiter or DomainRateLimiter(0)
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(timeout, connect=min(timeout, 8.0)),
            follow_redirects=False,
            headers={"User-Agent": user_agent, "Accept-Language": "en"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, url: str, *, accept: tuple[str, ...] = HTML_TYPES) -> FetchResult:
        redirects: list[str] = []
        current = url
        for _ in range(self.max_redirects + 1):
            target = await validate_url(current, self.resolver)
            await self.rate_limiter.wait(target.host)
            resp_info = await self._request_once(target, accept)
            if isinstance(resp_info, str):  # redirect location
                nxt = urljoin(current, resp_info)
                redirects.append(nxt)
                current = nxt
                continue
            status, ctype, text, truncated = resp_info
            return FetchResult(
                url=url,
                final_url=current,
                status_code=status,
                content_type=ctype,
                text=text,
                truncated=truncated,
                redirects=redirects,
            )
        raise FetchError("Too many redirects")

    async def _request_once(self, target: Target, accept: tuple[str, ...]):
        last_exc: Exception | None = None
        for ip in target.ips[:3]:
            pinned = f"{target.scheme}://{_ip_netloc(ip, target.port, target.scheme)}{target.path_qs}"
            default = 443 if target.scheme == "https" else 80
            host_header = target.host if target.port == default else f"{target.host}:{target.port}"
            try:
                async with self._client.stream(
                    "GET",
                    pinned,
                    headers={"Host": host_header, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8"},
                    extensions={"sni_hostname": target.host},
                ) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("location")
                        if not loc:
                            raise FetchError("Redirect without Location header")
                        return loc
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if resp.status_code < 400 and ctype and not ctype.startswith(accept):
                        raise FetchError(f"Unsupported content type: {ctype}")
                    declared = resp.headers.get("content-length")
                    truncated = bool(declared and declared.isdigit() and int(declared) > self.max_bytes)
                    buf = bytearray()
                    async for chunk in resp.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) >= self.max_bytes:
                            truncated = True
                            break
                    data = bytes(buf[: self.max_bytes])
                    encoding = resp.charset_encoding or "utf-8"
                    try:
                        text = data.decode(encoding, errors="replace")
                    except LookupError:
                        text = data.decode("utf-8", errors="replace")
                    return resp.status_code, ctype, text, truncated
            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                continue
            except httpx.HTTPError as exc:
                raise FetchError(f"HTTP error: {exc.__class__.__name__}") from exc
        raise FetchError(f"Connection failed: {last_exc.__class__.__name__}", transient=True)
