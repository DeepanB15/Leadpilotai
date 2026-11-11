"""Bounded website crawler: homepage + the most relevant internal pages."""

import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from app.enums import AccessStatus
from app.research.normalization.documents import NormalizedDoc
from app.research.safe_fetch import TEXT_TYPES, FetchError, SafeFetcher, UnsafeURLError
from app.research.website.extractor import MIN_USEFUL_CHARS, extract_content
from app.research.website.parser import parse_page, select_pages
from app.utils.text import content_hash

log = logging.getLogger(__name__)


class RobotsChecker:
    def __init__(self, fetcher: SafeFetcher, user_agent: str, enabled: bool = True):
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.enabled = enabled
        self._cache: dict[str, RobotFileParser | None] = {}

    async def allowed(self, url: str) -> bool:
        if not self.enabled:
            return True
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._cache:
            rp: RobotFileParser | None = None
            try:
                res = await self.fetcher.fetch(f"{origin}/robots.txt", accept=TEXT_TYPES)
                if res.ok:
                    rp = RobotFileParser()
                    rp.parse(res.text.splitlines())
            except (FetchError, UnsafeURLError):
                rp = None  # unreachable robots.txt => no restrictions
            self._cache[origin] = rp
        rp = self._cache[origin]
        return True if rp is None else rp.can_fetch(self.user_agent, url)


@dataclass
class CrawlError:
    url: str
    error: str


@dataclass
class CrawlResult:
    status: AccessStatus = AccessStatus.failed
    detail: str | None = None
    docs: list[NormalizedDoc] = field(default_factory=list)
    errors: list[CrawlError] = field(default_factory=list)
    social_urls: list[str] = field(default_factory=list)
    site_description: str | None = None


async def _fetch_doc(fetcher: SafeFetcher, robots: RobotsChecker, url: str, doc_type: str):
    """Return (NormalizedDoc | None, parsed | None, error | None)."""
    try:
        if not await robots.allowed(url):
            return None, None, "Disallowed by robots.txt"
        res = await fetcher.fetch(url)
    except UnsafeURLError as exc:
        return None, None, f"Blocked: {exc}"
    except FetchError as exc:
        return None, None, str(exc)
    if not res.ok:
        return None, None, f"HTTP {res.status_code}"
    parsed = parse_page(res.text, res.final_url)
    ex = extract_content(res.text, res.final_url)
    if len(ex.text) < MIN_USEFUL_CHARS:
        return None, parsed, "Page had no extractable content (possibly JavaScript-rendered)"
    doc = NormalizedDoc(
        document_type=doc_type,
        url=res.final_url,
        title=parsed.title,
        content=ex.text,
        metadata={
            "http_status": res.status_code,
            "extraction_method": ex.method,
            "truncated": ex.truncated or res.truncated,
            "meta_description": parsed.description,
            "content_type": res.content_type,
            "redirects": res.redirects,
        },
    )
    return doc, parsed, None


async def crawl_website(
    fetcher: SafeFetcher,
    robots: RobotsChecker,
    start_url: str,
    *,
    max_pages: int = 10,
    concurrency: int = 3,
) -> CrawlResult:
    result = CrawlResult()
    home, parsed, err = await _fetch_doc(fetcher, robots, start_url, "homepage")
    if home is None:
        result.errors.append(CrawlError(start_url, err or "unknown error"))
        result.detail = f"Homepage not collected: {err}"
        blocked = err and (err.startswith("Blocked") or err.startswith("HTTP 4") or "robots" in err)
        result.status = AccessStatus.inaccessible if blocked or (err and "Connection" in err) else AccessStatus.failed
        if parsed:  # homepage reachable but empty (JS-heavy): keep discovered social links
            result.social_urls = parsed.social_urls
            result.status = AccessStatus.partial
        return result

    seen_hashes = {content_hash(home.content)}
    seen_urls = {home.url.rstrip("/")}
    result.docs.append(home)
    result.social_urls = list(parsed.social_urls) if parsed else []
    result.site_description = parsed.description if parsed else None

    chosen = [
        (link, dt)
        for link, dt in select_pages(parsed.links if parsed else [], max(0, max_pages - 1))
        if link.url.rstrip("/") not in seen_urls
    ]
    sem = asyncio.Semaphore(concurrency)

    async def run(link, dt):
        async with sem:
            return link, await _fetch_doc(fetcher, robots, link.url, dt)

    outcomes = await asyncio.gather(*(run(link, dt) for link, dt in chosen), return_exceptions=True)
    socials = {u.lower(): u for u in result.social_urls}
    for item in outcomes:
        if isinstance(item, Exception):
            log.warning("page fetch crashed: %s", item)
            result.errors.append(CrawlError("?", f"{item.__class__.__name__}"))
            continue
        link, (doc, sub_parsed, sub_err) = item
        if sub_parsed:
            for u in sub_parsed.social_urls:
                socials.setdefault(u.lower(), u)
        if doc is None:
            result.errors.append(CrawlError(link.url, sub_err or "unknown error"))
            continue
        h = content_hash(doc.content)
        key = doc.url.rstrip("/")
        if h in seen_hashes or key in seen_urls:
            continue
        seen_hashes.add(h)
        seen_urls.add(key)
        result.docs.append(doc)
    result.social_urls = list(socials.values())

    result.status = AccessStatus.completed if not result.errors else AccessStatus.partial
    if result.errors:
        result.detail = f"{len(result.docs)} page(s) collected; {len(result.errors)} page(s) unavailable"
    if len(home.content) < 200 and len(result.docs) == 1:
        result.status = AccessStatus.partial
        result.detail = "Homepage content is very limited (possibly JavaScript-rendered)"
    return result
