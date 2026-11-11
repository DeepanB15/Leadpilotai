"""Profile identity verification. A name match alone is never sufficient."""

from app.enums import VerificationStatus
from app.utils.urls import domain_of, social_key


def assess_verification(url, profile, ctx) -> tuple[VerificationStatus, str]:
    if social_key(url) in ctx.website_social_keys:
        return VerificationStatus.verified, "Linked from the company's own website"

    site = None
    if profile is not None:
        if profile.website:
            site = domain_of(profile.website)
            if site and site == ctx.company_domain:
                return VerificationStatus.verified, "Profile links to the company website"
        desc = (profile.description or "").lower()
        if ctx.company_domain and ctx.company_domain.lower() in desc:
            return VerificationStatus.verified, "Profile description references the company domain"

    if site and site != ctx.company_domain:
        if ctx.user_supplied:
            return VerificationStatus.unverified, f"Profile links to a different website ({site})"
        return VerificationStatus.rejected, f"Profile links to a different website ({site})"
    return VerificationStatus.unverified, "No corroborating link between the profile and the company website"
