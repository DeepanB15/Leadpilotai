"""Social research adapter interface and shared result types.

Adapters implement only what their *actual* access mechanism supports. Anything
else yields an explicit ``unsupported`` / ``inaccessible`` outcome - never invented data.
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.enums import AccessStatus, VerificationStatus
from app.research.normalization.documents import NormalizedDoc
from app.research.social.verification import assess_verification


class UnsupportedPlatform(Exception):
    """No permitted integration exists for this platform in this deployment."""


class AccessUnavailable(Exception):
    """The platform/profile cannot be accessed right now (auth, quota, not found, private...)."""


@dataclass
class SocialContext:
    company_name: str
    company_domain: str
    website_social_keys: set[str] = field(default_factory=set)
    user_supplied: bool = False
    limit: int = 8


@dataclass
class ProfileInfo:
    platform: str
    url: str
    display_name: str | None = None
    description: str | None = None
    website: str | None = None
    handle: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ContentItem:
    url: str
    text: str
    title: str | None = None
    published_at: datetime | None = None
    doc_type: str = "post"
    metadata: dict = field(default_factory=dict)


@dataclass
class AdapterOutcome:
    platform: str
    url: str
    access_status: AccessStatus
    verification_status: VerificationStatus = VerificationStatus.unverified
    verification_reason: str | None = None
    detail: str | None = None
    profile: ProfileInfo | None = None
    content: list[ContentItem] = field(default_factory=list)

    def to_documents(self) -> list[NormalizedDoc]:
        docs: list[NormalizedDoc] = []
        if self.profile and self.verification_status != VerificationStatus.rejected:
            p = self.profile
            lines = [f"{self.platform.title()} profile: {p.display_name or p.handle or p.url}"]
            if p.description:
                lines.append(p.description)
            if p.website:
                lines.append(f"Website: {p.website}")
            text = "\n".join(lines)
            if len(text) >= 20:
                docs.append(
                    NormalizedDoc(
                        document_type="social_profile",
                        url=p.url,
                        title=p.display_name,
                        content=text,
                        metadata={"platform": self.platform, "verification": self.verification_status.value, **p.metadata},
                    )
                )
            for item in self.content:
                body = "\n".join(x for x in (item.title, item.text) if x).strip()
                if len(body) < 10:
                    continue
                docs.append(
                    NormalizedDoc(
                        document_type=item.doc_type,
                        url=item.url,
                        title=item.title,
                        content=body,
                        published_at=item.published_at,
                        metadata={"platform": self.platform, **item.metadata},
                    )
                )
        return docs


class SocialResearchAdapter:
    platform: str = ""

    async def verify_profile(
        self, url: str, ctx: SocialContext, profile: ProfileInfo | None = None
    ) -> tuple[VerificationStatus, str]:
        return assess_verification(url, profile, ctx)

    async def fetch_profile(self, url: str) -> ProfileInfo:
        raise NotImplementedError

    async def fetch_recent_content(self, url: str, limit: int) -> list[ContentItem]:
        raise NotImplementedError

    async def research(self, url: str, ctx: SocialContext) -> AdapterOutcome:
        """Run verify -> profile -> content with full failure isolation."""
        out = AdapterOutcome(platform=self.platform, url=url, access_status=AccessStatus.failed)
        profile: ProfileInfo | None = None
        try:
            profile = await self.fetch_profile(url)
            out.profile = profile
        except (NotImplementedError, UnsupportedPlatform) as exc:
            out.access_status = AccessStatus.unsupported
            out.detail = str(exc) or "No permitted integration is configured for this platform."
        except AccessUnavailable as exc:
            out.access_status = AccessStatus.inaccessible
            out.detail = str(exc)
        except Exception as exc:  # isolate adapter bugs/network errors
            out.access_status = AccessStatus.failed
            out.detail = f"{exc.__class__.__name__}: {exc}"[:300]

        out.verification_status, out.verification_reason = await self.verify_profile(url, ctx, profile)
        if profile is None:
            return out
        if out.verification_status == VerificationStatus.rejected:
            out.access_status = AccessStatus.completed
            out.detail = f"Profile not associated with the company: {out.verification_reason}"
            return out

        try:
            out.content = await self.fetch_recent_content(url, ctx.limit)
            out.access_status = AccessStatus.completed
        except (NotImplementedError, UnsupportedPlatform):
            out.access_status = AccessStatus.partial
            out.detail = "Profile collected; content collection is not supported for this platform."
        except AccessUnavailable as exc:
            out.access_status = AccessStatus.partial
            out.detail = f"Profile collected; content unavailable: {exc}"
        except Exception as exc:
            out.access_status = AccessStatus.partial
            out.detail = f"Profile collected; content failed: {exc.__class__.__name__}"
        return out


class UnsupportedAdapter(SocialResearchAdapter):
    reason = "No permitted integration is configured for this platform."

    async def fetch_profile(self, url: str) -> ProfileInfo:
        raise UnsupportedPlatform(self.reason)
