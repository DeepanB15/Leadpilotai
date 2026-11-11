"""Unified Company Intelligence Report: coverage, limitations, assembly and persistence."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.enums import ALL_PLATFORMS, AccessStatus, VerificationStatus
from app.intelligence.docs import DocRef
from app.models import Company, ResearchReport, ResearchSource
from app.utils.time import utcnow
from app.utils.urls import PLATFORM_LABELS


def build_coverage(sources: list[ResearchSource], doc_counts: dict[uuid.UUID, int] | None = None) -> list[dict]:
    doc_counts = doc_counts or {}
    by_platform: dict[str, ResearchSource] = {}
    for s in sorted(sources, key=lambda s: s.last_checked_at or s.created_at):
        by_platform[s.platform] = s  # latest checked wins
    out = []
    for p in ALL_PLATFORMS:
        s = by_platform.get(p.value)
        if s is None:
            out.append(
                {
                    "platform": p.value,
                    "status": AccessStatus.not_discovered.value,
                    "source_url": None,
                    "verification_status": None,
                    "detail": None,
                    "last_checked_at": None,
                    "documents": 0,
                }
            )
        else:
            out.append(
                {
                    "platform": p.value,
                    "status": s.access_status,
                    "source_url": s.source_url,
                    "verification_status": s.verification_status,
                    "detail": s.status_detail,
                    "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
                    "documents": doc_counts.get(s.id, 0),
                }
            )
    return out


def build_limitations(coverage: list[dict], *, analysis_error: str | None = None, has_profile: bool = True) -> list[str]:
    notes: list[str] = []
    for c in coverage:
        p, status, detail = c["platform"], c["status"], c.get("detail")
        label = PLATFORM_LABELS[p]
        d = f" ({detail})" if detail else ""
        if p == "website":
            if status in ("failed", "inaccessible"):
                notes.append(f"The company website could not be accessed{d}; website-based findings are unavailable.")
            elif status == "partial":
                notes.append(f"Website research was partial{d}; some pages were not collected.")
            elif status == "not_discovered":
                notes.append("No website research was recorded.")
            continue
        if status == "not_discovered":
            notes.append(
                f"No {label} profile was discovered or supplied. This does not mean the company has no {label} presence."
            )
        elif status == "inaccessible":
            notes.append(f"{label} could not be accessed{d}; its presence and content are not assessed.")
        elif status == "unsupported":
            notes.append(
                f"A {label} profile URL was recorded, but no permitted integration is available in v1{d}; "
                "its content is not assessed."
            )
        elif status == "failed":
            notes.append(f"{label} research failed{d}; it is not assessed.")
        elif status == "partial":
            notes.append(f"{label} research was partial{d}.")
        if c.get("verification_status") == "rejected":
            notes.append(f"A {label} profile was found but could not be tied to this company; it was excluded.")
        elif c.get("verification_status") == "unverified" and status in ("completed", "partial"):
            notes.append(
                f"The {label} profile could not be verified as official; findings that rely on it have lower confidence."
            )
    if analysis_error:
        notes.append(f"AI analysis was unavailable or invalid ({analysis_error}); no profile or insights were generated.")
    elif not has_profile:
        notes.append("No company profile was generated.")
    return notes


def coverage_note(coverage: list[dict]) -> str:
    lines = []
    for c in coverage:
        lines.append(f"- {PLATFORM_LABELS[c['platform']]}: {c['status']}")
    return "\n".join(lines)


def assemble_report(
    *,
    company: Company,
    job_status: str,
    profile_data: dict | None,
    profile_fields: list[dict] | None,
    profile_version: int | None,
    findings: list[dict],
    sales_preparation: dict | None,
    coverage: list[dict],
    docs: list[DocRef],
    limitations: list[str],
    analysis_error: str | None,
    model_id: str | None,
    settings: Settings,
) -> dict[str, Any]:
    overview: dict[str, Any] = {
        "name": company.name,
        "website": company.website_url,
        "domain": company.normalized_domain,
        "industry": company.industry,
    }
    if profile_data:
        ov = profile_data.get("company_overview", {})
        overview.update(
            {
                "description": ov.get("description", "unknown"),
                "industry": ov.get("industry") if ov.get("industry", "unknown") != "unknown" else company.industry,
                "business_model": ov.get("business_model", "unknown"),
                "target_audience": ov.get("target_audience", []),
                "products": profile_data.get("products", []),
                "services": profile_data.get("services", []),
                "market_positioning": profile_data.get("market_positioning", "unknown"),
                "digital_presence": profile_data.get("digital_presence", {}),
                "content_themes": profile_data.get("content_themes", []),
            }
        )
    return {
        "overview": overview,
        "research_coverage": coverage,
        "findings": findings,
        "sales_preparation": sales_preparation
        or {"talking_points": [], "prospect_questions": [], "value_proposition": None, "suggested_next_action": None},
        "limitations": limitations,
        "sources": [
            {
                "document_id": str(d.id),
                "platform": d.platform,
                "document_type": d.document_type,
                "url": d.url,
                "title": d.title,
                "collected_at": d.collected_at.isoformat(),
                "published_at": d.published_at.isoformat() if d.published_at else None,
                "verification_status": d.verification_status,
            }
            for d in docs
        ],
        "profile": {"version": profile_version, "fields": profile_fields or []},
        "analysis": {"status": "unavailable" if analysis_error or not profile_data else "completed", "error": analysis_error},
        "job_status": job_status,
        "model_id": model_id,
        "prompt_version": settings.prompt_version,
        "schema_version": settings.schema_version,
        "pipeline_version": settings.pipeline_version,
        "generated_at": utcnow().isoformat(),
    }


def save_report(db: Session, company: Company, job_id: uuid.UUID, data: dict) -> ResearchReport:
    version = (db.scalar(select(func.max(ResearchReport.version)).where(ResearchReport.company_id == company.id)) or 0) + 1
    row = ResearchReport(
        company_id=company.id, job_id=job_id, user_id=company.user_id, version=version, report_data=data
    )
    db.add(row)
    db.flush()
    return row


def finding_to_dict(row) -> dict:
    return {
        "id": str(row.id),
        "finding_type": row.finding_type,
        "classification": row.classification,
        "title": row.title,
        "description": row.description,
        "evidence": row.evidence,
        "confidence": row.confidence,
        "confidence_factors": row.confidence_factors,
        "review_status": getattr(row, "review_status", "unreviewed"),
    }


__all__ = [
    "VerificationStatus",
    "assemble_report",
    "build_coverage",
    "build_limitations",
    "coverage_note",
    "finding_to_dict",
    "save_report",
]
