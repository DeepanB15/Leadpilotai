"""YouTube adapter using the official YouTube Data API v3 (public channel + upload data)."""

from datetime import datetime
from urllib.parse import urlsplit

import httpx

from app.research.social.base import (
    AccessUnavailable,
    ContentItem,
    ProfileInfo,
    SocialResearchAdapter,
)

API = "https://www.googleapis.com/youtube/v3"


def _parse_channel_ref(url: str) -> dict:
    segs = [s for s in urlsplit(url).path.split("/") if s]
    if not segs:
        raise AccessUnavailable("Unrecognized YouTube URL")
    if segs[0].startswith("@"):
        return {"forHandle": segs[0]}
    if segs[0] == "channel" and len(segs) >= 2:
        return {"id": segs[1]}
    if segs[0] == "user" and len(segs) >= 2:
        return {"forUsername": segs[1]}
    raise AccessUnavailable(
        "Custom channel URLs (/c/...) cannot be resolved with the official API; "
        "supply a /channel/<id> or /@handle URL"
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class YouTubeAdapter(SocialResearchAdapter):
    platform = "youtube"

    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 12.0):
        self.api_key = api_key
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)
        self._uploads: dict[str, str] = {}

    async def _get(self, path: str, params: dict) -> dict:
        if not self.api_key:
            raise AccessUnavailable("YouTube API key is not configured (set YOUTUBE_API_KEY)")
        resp = await self._client.get(f"{API}/{path}", params={**params, "key": self.api_key})
        if resp.status_code in (400, 401, 403, 404):
            reason = ""
            try:
                reason = resp.json()["error"]["errors"][0]["reason"]
            except Exception:
                pass
            raise AccessUnavailable(f"YouTube API refused the request ({resp.status_code} {reason})".strip())
        resp.raise_for_status()
        return resp.json()

    async def fetch_profile(self, url: str) -> ProfileInfo:
        ref = _parse_channel_ref(url)
        data = await self._get("channels", {"part": "snippet,contentDetails", **ref})
        items = data.get("items") or []
        if not items:
            raise AccessUnavailable("Channel not found or not public")
        ch = items[0]
        sn = ch.get("snippet", {})
        uploads = ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if uploads:
            self._uploads[url] = uploads
        custom = sn.get("customUrl")
        return ProfileInfo(
            platform="youtube",
            url=url,
            display_name=sn.get("title"),
            description=(sn.get("description") or "").strip() or None,
            handle=custom,
            metadata={
                "channel_id": ch.get("id"),
                "custom_url": custom,
                "channel_created_at": sn.get("publishedAt"),
                "country": sn.get("country"),
            },
        )

    async def fetch_recent_content(self, url: str, limit: int) -> list[ContentItem]:
        uploads = self._uploads.get(url)
        if not uploads:
            await self.fetch_profile(url)
            uploads = self._uploads.get(url)
        if not uploads:
            raise AccessUnavailable("Channel has no accessible uploads playlist")
        data = await self._get(
            "playlistItems", {"part": "snippet,contentDetails", "playlistId": uploads, "maxResults": min(limit, 25)}
        )
        out: list[ContentItem] = []
        for it in data.get("items", []):
            sn = it.get("snippet", {})
            vid = it.get("contentDetails", {}).get("videoId") or sn.get("resourceId", {}).get("videoId")
            if not vid or sn.get("title") in ("Private video", "Deleted video"):
                continue
            out.append(
                ContentItem(
                    url=f"https://www.youtube.com/watch?v={vid}",
                    title=sn.get("title"),
                    text=(sn.get("description") or "").strip(),
                    published_at=_parse_dt(it.get("contentDetails", {}).get("videoPublishedAt") or sn.get("publishedAt")),
                    doc_type="video",
                    metadata={"video_id": vid},
                )
            )
        return out
