"""URL normalization and social-profile classification."""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_BAD_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home.arpa", ".invalid", ".example")


class InvalidURL(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedSite:
    url: str  # e.g. https://www.acme.com
    host: str  # www.acme.com
    domain: str  # acme.com (host without leading www.)


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def _clean_host(host: str) -> str:
    host = host.strip().rstrip(".").lower()
    if not host:
        raise InvalidURL("Missing hostname")
    if _is_ip(host):
        raise InvalidURL("IP addresses are not accepted; use a domain name")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidURL("Invalid hostname") from exc
    if "." not in host:
        raise InvalidURL("Hostname must be a fully qualified domain name")
    if host == "localhost" or host.endswith(_BAD_SUFFIXES):
        raise InvalidURL("Hostname is not a public domain")
    labels = host.split(".")
    if not all(_LABEL.match(label) for label in labels) or len(labels[-1]) < 2 or len(host) > 253:
        raise InvalidURL("Invalid hostname")
    return host


def normalize_website(raw: str) -> NormalizedSite:
    s = (raw or "").strip()
    if not s:
        raise InvalidURL("Website URL is required")
    if "://" not in s:
        s = "https://" + s.lstrip("/")
    try:
        p = urlsplit(s)
        port = p.port
    except ValueError as exc:
        raise InvalidURL("Invalid URL") from exc
    if p.scheme not in ("http", "https"):
        raise InvalidURL("Only http and https URLs are supported")
    if p.username or p.password:
        raise InvalidURL("URLs with credentials are not accepted")
    if port not in (None, 80, 443):
        raise InvalidURL("Only standard ports (80/443) are supported")
    host = _clean_host(p.hostname or "")
    path = p.path.rstrip("/")
    url = f"{p.scheme}://{host}{path}"
    domain = host[4:] if host.startswith("www.") else host
    return NormalizedSite(url=url, host=host, domain=domain)


def domain_of(url: str) -> str | None:
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def same_site(a: str, b: str) -> bool:
    da, db = domain_of(a), domain_of(b)
    return bool(da and db and da == db)


# ---------------------------------------------------------------- social URLs

_YT_RESERVED = {"watch", "playlist", "results", "feed", "shorts", "embed", "live", "hashtag"}
_IG_RESERVED = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "direct", "about", "legal", "developer"}
_FB_RESERVED = {
    "sharer", "sharer.php", "share", "share.php", "dialog", "plugins", "tr", "login", "login.php", "events",
    "groups", "watch", "marketplace", "policies", "help", "privacy", "pages", "photo", "photo.php", "permalink.php",
}  # fmt: skip
_X_RESERVED = {
    "intent", "share", "home", "search", "i", "hashtag", "explore", "login", "settings", "messages",
    "notifications", "tos", "privacy", "compose",
}  # fmt: skip

PLATFORM_LABELS = {
    "linkedin": "LinkedIn",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "facebook": "Facebook",
    "x": "X",
    "website": "Website",
}


def classify_social_url(raw: str) -> tuple[str, str] | None:
    """Return (platform, canonical_url) for a company/channel profile URL, else None."""
    s = (raw or "").strip()
    if not s:
        return None
    if "://" not in s:
        s = "https://" + s.lstrip("/")
    try:
        p = urlsplit(s)
    except ValueError:
        return None
    if p.scheme not in ("http", "https"):
        return None
    host = (p.hostname or "").lower()
    for prefix in ("www.", "m.", "mobile."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    segs = [x for x in p.path.split("/") if x]

    if host == "linkedin.com":
        if len(segs) >= 2 and segs[0] in ("company", "school", "showcase"):
            return "linkedin", f"https://www.linkedin.com/{segs[0]}/{segs[1]}"
    elif host == "instagram.com":
        if segs and segs[0].lower() not in _IG_RESERVED:
            return "instagram", f"https://www.instagram.com/{segs[0]}"
    elif host == "youtube.com":
        if segs:
            if segs[0].startswith("@") and len(segs[0]) > 1:
                return "youtube", f"https://www.youtube.com/{segs[0]}"
            if segs[0] == "channel" and len(segs) >= 2:
                return "youtube", f"https://www.youtube.com/channel/{segs[1]}"
            if segs[0] in ("c", "user") and len(segs) >= 2:
                return "youtube", f"https://www.youtube.com/{segs[0]}/{segs[1]}"
    elif host in ("facebook.com", "fb.com"):
        if segs and segs[0].lower() not in _FB_RESERVED:
            return "facebook", f"https://www.facebook.com/{segs[0]}"
    elif host in ("x.com", "twitter.com"):
        if segs and segs[0].lower() not in _X_RESERVED:
            return "x", f"https://x.com/{segs[0]}"
    return None


def social_key(url: str) -> str:
    """Case-insensitive identity key for comparing profile URLs."""
    c = classify_social_url(url)
    return (c[1] if c else url).lower().rstrip("/")


def validate_social_field(platform: str, raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    c = classify_social_url(raw)
    if not c or c[0] != platform:
        raise InvalidURL(f"Not a valid {PLATFORM_LABELS[platform]} profile URL")
    return c[1]
