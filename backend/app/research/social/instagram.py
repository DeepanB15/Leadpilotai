from app.research.social.base import UnsupportedAdapter


class InstagramAdapter(UnsupportedAdapter):
    platform = "instagram"
    reason = (
        "Instagram content requires the Instagram Graph API with account authorization; "
        "not collected in v1. The profile URL is recorded as a source only."
    )
