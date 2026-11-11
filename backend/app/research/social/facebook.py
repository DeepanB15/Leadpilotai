from app.research.social.base import UnsupportedAdapter


class FacebookAdapter(UnsupportedAdapter):
    platform = "facebook"
    reason = (
        "Facebook Page content requires the Graph API with page access tokens; "
        "not collected in v1. The page URL is recorded as a source only."
    )
