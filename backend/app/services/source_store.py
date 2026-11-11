"""Persistence helpers for research sources and normalized documents."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AccessStatus, VerificationStatus
from app.models import Company, ResearchJob, ResearchSource, SourceDocument
from app.research.normalization.documents import NormalizedDoc
from app.utils.time import utcnow


def upsert_source(
    db: Session,
    *,
    company: Company,
    job: ResearchJob,
    source_type: str,
    platform: str,
    url: str,
    discovery_method: str | None,
    verification: VerificationStatus,
    access: AccessStatus,
    detail: str | None = None,
    profile_metadata: dict | None = None,
) -> ResearchSource:
    src = db.scalar(
        select(ResearchSource).where(
            ResearchSource.company_id == company.id,
            ResearchSource.platform == platform,
            ResearchSource.source_url == url,
        )
    )
    if src is None:
        src = ResearchSource(
            company_id=company.id,
            user_id=company.user_id,
            source_type=source_type,
            platform=platform,
            source_url=url,
        )
        db.add(src)
    src.job_id = job.id
    src.discovery_method = discovery_method
    src.verification_status = verification.value
    src.access_status = access.value
    src.status_detail = detail
    src.profile_metadata = profile_metadata
    src.last_checked_at = utcnow()
    db.flush()
    return src


def update_source(
    db: Session, src: ResearchSource, *, access: AccessStatus, detail: str | None, verification=None, metadata=None
) -> None:
    src.access_status = access.value
    src.status_detail = detail
    src.last_checked_at = utcnow()
    if verification is not None:
        src.verification_status = verification.value
    if metadata is not None:
        src.profile_metadata = metadata
    db.flush()


def save_documents(db: Session, src: ResearchSource, company: Company, docs: list[NormalizedDoc]) -> list[SourceDocument]:
    """Insert new documents; refresh ones whose content hash is already stored for this source."""
    saved: list[SourceDocument] = []
    now = utcnow()
    existing = {
        d.content_hash: d for d in db.scalars(select(SourceDocument).where(SourceDocument.source_id == src.id))
    }
    for nd in docs:
        h = nd.content_hash
        row = existing.get(h)
        if row is None:
            row = SourceDocument(
                source_id=src.id,
                company_id=company.id,
                user_id=company.user_id,
                document_type=nd.document_type,
                url=nd.url,
                title=nd.title,
                content=nd.content,
                content_hash=h,
                published_at=nd.published_at,
                collected_at=now,
                meta={**nd.metadata, "content_length": len(nd.content)},
            )
            db.add(row)
            existing[h] = row
        else:
            row.collected_at = now
            row.title = nd.title or row.title
            row.url = nd.url
            row.meta = {**(row.meta or {}), **nd.metadata, "content_length": len(nd.content)}
        saved.append(row)
    db.flush()
    return saved
