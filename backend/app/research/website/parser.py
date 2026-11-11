"""HTML parsing: title/description, link discovery, social links, page classification."""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup

from app.utils.urls import classify_social_url, same_site

SKIP_EXT = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip", ".mp4", ".mp3", ".css", ".js", ".xml",
    ".ico", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
)  # fmt: skip


@dataclass
class Link:
    url: str
    text: str


@dataclass
class ParsedPage:
    title: str | None = None
    description: str | None = None
    links: list[Link] = field(default_factory=list)  # internal only
    social_urls: list[str] = field(default_factory=list)  # canonical, any platform


def _collect_sameas(node, out: list[str]) -> None:
    if isinstance(node, dict):
        same = node.get("sameAs")
        if isinstance(same, str):
            out.append(same)
        elif isinstance(same, list):
            out.extend(x for x in same if isinstance(x, str))
        for v in node.values():
            _collect_sameas(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_sameas(v, out)


def parse_page(html: str, base_url: str) -> ParsedPage:
    soup = BeautifulSoup(html, "html.parser")
    page = ParsedPage()

    if soup.title and soup.title.string:
        page.title = " ".join(soup.title.string.split())[:300] or None
    if not page.title:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            page.title = " ".join(og["content"].split())[:300]
    desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if desc and desc.get("content"):
        page.description = " ".join(desc["content"].split())[:500]

    seen_links: set[str] = set()
    socials: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "sms:")):
            continue
        absolute, _ = urldefrag(urljoin(base_url, href))
        try:
            parts = urlsplit(absolute)
        except ValueError:
            continue
        if parts.scheme not in ("http", "https"):
            continue
        cls = classify_social_url(absolute)
        if cls:
            socials.setdefault(cls[1].lower(), cls[1])
            continue
        if not same_site(absolute, base_url):
            continue
        if parts.path.lower().endswith(SKIP_EXT):
            continue
        norm = absolute.rstrip("/") if parts.path not in ("", "/") else absolute.rstrip("/")
        if norm in seen_links:
            continue
        seen_links.add(norm)
        page.links.append(Link(url=norm, text=" ".join(a.get_text(" ").split())[:120]))

    # JSON-LD sameAs
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        urls: list[str] = []
        _collect_sameas(data, urls)
        for u in urls:
            cls = classify_social_url(u)
            if cls:
                socials.setdefault(cls[1].lower(), cls[1])

    page.social_urls = list(socials.values())
    return page


# ----------------------------------------------------------- classification

_RULES: list[tuple[str, int, re.Pattern]] = [
    ("about_page", 1, re.compile(r"(^|/)(about|about-us|company|who-we-are|our-story|team|mission)(/|$|-)")),
    ("product_page", 2, re.compile(r"(^|/)(products?|platform|features?|software|tools?)(/|$|-)")),
    ("services_page", 3, re.compile(r"(^|/)(services?|consulting|what-we-do|offerings?)(/|$|-)")),
    ("solutions_page", 4, re.compile(r"(^|/)(solutions?|use-cases?|industries|customers?)(/|$|-)")),
    ("pricing_page", 5, re.compile(r"(^|/)(pricing|plans|prices?)(/|$|-)")),
    ("contact_page", 6, re.compile(r"(^|/)(contact|contact-us|get-in-touch|demo|book-a-demo)(/|$|-)")),
    ("blog_post", 7, re.compile(r"(^|/)(blog|news|press|insights|resources|newsroom)(/|$|-)")),
]

MAX_PER_TYPE = {"blog_post": 2}


def classify_page(url: str, anchor_text: str = "") -> tuple[str, int]:
    path = urlsplit(url).path.lower()
    depth = len([s for s in path.split("/") if s])
    if depth > 3:
        return "other_page", 99
    for doc_type, prio, rx in _RULES:
        if rx.search(path):
            return doc_type, prio
    text = anchor_text.lower().strip()
    if depth <= 1 and text:
        for doc_type, prio, rx in _RULES:
            if rx.search("/" + re.sub(r"\s+", "-", text)):
                return doc_type, prio
    return "other_page", 99


def select_pages(links: list[Link], limit: int, per_type: int = 2) -> list[tuple[Link, str]]:
    """Choose the most relevant internal pages (priority order, capped per type)."""
    scored: list[tuple[int, int, Link, str]] = []
    for link in links:
        doc_type, prio = classify_page(link.url, link.text)
        if prio >= 99:
            continue
        scored.append((prio, len(urlsplit(link.url).path), link, doc_type))
    scored.sort(key=lambda t: (t[0], t[1]))
    counts: dict[str, int] = {}
    chosen: list[tuple[Link, str]] = []
    for _, _, link, doc_type in scored:
        cap = MAX_PER_TYPE.get(doc_type, per_type)
        if counts.get(doc_type, 0) >= cap:
            continue
        counts[doc_type] = counts.get(doc_type, 0) + 1
        chosen.append((link, doc_type))
        if len(chosen) >= limit:
            break
    return chosen
