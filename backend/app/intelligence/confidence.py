"""Deterministic confidence scoring (documented in IMPLEMENTATION_PLAN.md).

Points
  +2  evidence from a first-party website page
  +1  evidence from a verified social profile
  +1  per additional independent source (max 2)         [independent = distinct research source]
  +1  consistent across sources (>=2 sources, no contradiction flagged)
  +1  evidence collected/published within 90 days
  -2  contradicting evidence flagged
  -1  extraction partial or truncated
Label: >=5 high, 3-4 medium, <=2 low.  Inference is capped at medium.  Unknown is always low.
"""

from datetime import datetime, timedelta

from app.intelligence.docs import DocRef

RECENT_DAYS = 90


def label_for(points: int) -> str:
    if points >= 5:
        return "high"
    if points >= 3:
        return "medium"
    return "low"


def score_finding(
    classification: str,
    docs: list[DocRef],
    *,
    contradicted: bool = False,
    now: datetime,
) -> tuple[str, dict]:
    if classification == "unknown" or not docs:
        return "low", {"points": 0, "reason": "No supporting evidence", "breakdown": {}}

    breakdown: dict[str, int] = {}
    if any(d.platform == "website" for d in docs):
        breakdown["first_party_website_evidence"] = 2
    if any(d.platform != "website" and d.verification_status == "verified" for d in docs):
        breakdown["verified_social_evidence"] = 1

    sources = {d.source_id for d in docs}
    extra = min(max(len(sources) - 1, 0), 2)
    if extra:
        breakdown["additional_independent_sources"] = extra
    if len(sources) >= 2 and not contradicted:
        breakdown["consistent_across_sources"] = 1

    cutoff = now - timedelta(days=RECENT_DAYS)
    if any((d.published_at or d.collected_at) >= cutoff for d in docs):
        breakdown["recent_evidence"] = 1
    if contradicted:
        breakdown["contradicting_evidence"] = -2
    if any(d.metadata.get("truncated") or d.source_access_status == "partial" for d in docs):
        breakdown["partial_or_truncated_extraction"] = -1

    points = sum(breakdown.values())
    label = label_for(points)
    capped = False
    if classification == "inference" and label == "high":
        label, capped = "medium", True
    return label, {
        "points": points,
        "breakdown": breakdown,
        "independent_sources": len(sources),
        "capped_for_inference": capped,
    }
