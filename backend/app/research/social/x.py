from app.research.social.base import UnsupportedAdapter


class XAdapter(UnsupportedAdapter):
    platform = "x"
    reason = (
        "X requires paid API access that is not configured in v1; "
        "the profile URL is recorded as a source only."
    )
