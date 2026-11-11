"""Main-content extraction (Trafilatura, with a BeautifulSoup fallback) and cleaning."""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.utils.text import truncate

MAX_DOC_CHARS = 20_000
MIN_USEFUL_CHARS = 80

_NOISE_TAGS = ["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe", "template"]


@dataclass
class Extracted:
    text: str
    method: str
    truncated: bool


def _clean(text: str) -> str:
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if not ln:
            continue
        if out and out[-1] == ln:
            continue
        out.append(ln)
    return "\n".join(out)


def _fallback(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return _clean(main.get_text("\n"))


def extract_content(html: str, url: str) -> Extracted:
    text = ""
    method = "trafilatura"
    try:
        import trafilatura

        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
            output_format="txt",
        ) or ""
    except Exception:  # extraction must never crash the crawl
        text = ""
    text = _clean(text)
    if len(text) < 200:
        fb = _fallback(html)
        if len(fb) > len(text):
            text, method = fb, "bs4_fallback"
    text, truncated = truncate(text, MAX_DOC_CHARS)
    return Extracted(text=text, method=method, truncated=truncated)
