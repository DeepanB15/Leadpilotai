from app.research.social.base import UnsupportedAdapter


class LinkedInAdapter(UnsupportedAdapter):
    platform = "linkedin"
    reason = (
        "LinkedIn does not offer public profile/content access without authenticated partner API access; "
        "not collected in v1. The profile URL is recorded as a source only."
    )
