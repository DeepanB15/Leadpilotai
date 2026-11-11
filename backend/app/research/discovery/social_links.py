"""Social source discovery: user-supplied URLs + links found on the company's website."""

from dataclasses import dataclass

from app.enums import SOCIAL_PLATFORMS
from app.utils.urls import classify_social_url, social_key


@dataclass
class DiscoveredSocial:
    platform: str
    url: str
    method: str  # user_supplied | website_link
    user_supplied: bool


def discover_social_sources(
    user_urls: dict[str, str], website_urls: list[str]
) -> tuple[list[DiscoveredSocial], set[str]]:
    """Return one discovered profile per platform plus the set of website-linked profile keys."""
    website_by_platform: dict[str, str] = {}
    website_keys: set[str] = set()
    for u in website_urls:
        c = classify_social_url(u)
        if not c:
            continue
        website_keys.add(social_key(c[1]))
        website_by_platform.setdefault(c[0], c[1])

    found: list[DiscoveredSocial] = []
    for platform in SOCIAL_PLATFORMS:
        p = platform.value
        if user_urls.get(p):
            found.append(DiscoveredSocial(p, user_urls[p], "user_supplied", True))
        elif p in website_by_platform:
            found.append(DiscoveredSocial(p, website_by_platform[p], "website_link", False))
    return found, website_keys
