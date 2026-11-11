from app.core.config import Settings
from app.research.social.base import SocialResearchAdapter
from app.research.social.facebook import FacebookAdapter
from app.research.social.instagram import InstagramAdapter
from app.research.social.linkedin import LinkedInAdapter
from app.research.social.x import XAdapter
from app.research.social.youtube import YouTubeAdapter


def build_adapters(settings: Settings) -> dict[str, SocialResearchAdapter]:
    return {
        "linkedin": LinkedInAdapter(),
        "instagram": InstagramAdapter(),
        "youtube": YouTubeAdapter(settings.youtube_api_key),
        "facebook": FacebookAdapter(),
        "x": XAdapter(),
    }
