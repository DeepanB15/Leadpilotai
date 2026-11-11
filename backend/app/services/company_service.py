import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Duplicate, NotFound
from app.enums import ACTIVE_STATUSES, JobStatus
from app.models import (
    Company,
    CompanyProfile,
    ResearchFinding,
    ResearchJob,
    ResearchReport,
    ResearchSource,
    SourceDocument,
)
from app.schemas.company import CompanyCreate, CompanyOut, CompanyUpdate
from app.utils.urls import normalize_website

PROCESSING = [s.value for s in ACTIVE_STATUSES if s != JobStatus.queued]


def find_by_domain(db: Session, user_id: uuid.UUID, domain: str) -> Company | None:
    return db.scalar(select(Company).where(Company.user_id == user_id, Company.normalized_domain == domain))


def create_company(db: Session, user_id: uuid.UUID, data: CompanyCreate) -> Company:
    domain = normalize_website(data.website_url).domain
    existing = find_by_domain(db, user_id, domain)
    if existing:
        raise Duplicate(
            f"A company with domain {domain} already exists", details={"existing_company_id": str(existing.id)}
        )
    company = Company(user_id=user_id, normalized_domain=domain, **data.model_dump())
    db.add(company)
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent insert
        db.rollback()
        existing = find_by_domain(db, user_id, domain)
        raise Duplicate(
            f"A company with domain {domain} already exists",
            details={"existing_company_id": str(existing.id) if existing else None},
        ) from exc
    db.refresh(company)
    return company


def get_company(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> Company:
    company = db.scalar(select(Company).where(Company.id == company_id, Company.user_id == user_id))
    if not company:
        raise NotFound("Company not found")
    return company


def _status_filter(status: str):
    if status == "pending":
        return Company.latest_status.is_(None)
    if status == "processing":
        return Company.latest_status.in_(PROCESSING)
    return Company.latest_status == status


def list_companies(
    db: Session,
    user_id: uuid.UUID,
    *,
    q: str | None,
    status: str | None,
    limit: int,
    offset: int,
    sort: str = "-created_at",
) -> tuple[list[CompanyOut], int]:
    stmt = select(Company).where(Company.user_id == user_id)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Company.name).like(like), Company.normalized_domain.like(like)))
    if status:
        stmt = stmt.where(_status_filter(status))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_map = {
        "created_at": Company.created_at,
        "name": func.lower(Company.name),
        "last_researched_at": Company.last_researched_at,
        "status": Company.latest_status,
    }
    desc = sort.startswith("-")
    col = sort_map.get(sort.lstrip("-"), Company.created_at)
    stmt = stmt.order_by(col.desc() if desc else col.asc(), Company.id).limit(limit).offset(offset)
    rows = list(db.scalars(stmt))

    platforms = _platforms(db, user_id, [c.id for c in rows])
    items = []
    for c in rows:
        out = CompanyOut.model_validate(c)
        supplied = set(c.social_urls().keys())
        out.platforms = sorted(supplied | platforms.get(c.id, set()))
        items.append(out)
    return items, total


def _platforms(db: Session, user_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[uuid.UUID, set[str]]:
    if not ids:
        return {}
    out: dict[uuid.UUID, set[str]] = {}
    rows = db.execute(
        select(ResearchSource.company_id, ResearchSource.platform).where(
            ResearchSource.user_id == user_id,
            ResearchSource.company_id.in_(ids),
            ResearchSource.platform != "website",
            ResearchSource.verification_status != "rejected",
        )
    )
    for cid, platform in rows:
        out.setdefault(cid, set()).add(platform)
    return out


def update_company(db: Session, user_id: uuid.UUID, company_id: uuid.UUID, data: CompanyUpdate) -> Company:
    company = get_company(db, user_id, company_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        changes.pop("name")
    if "website_url" in changes:
        if changes["website_url"] is None:
            changes.pop("website_url")
        else:
            domain = normalize_website(changes["website_url"]).domain
            other = find_by_domain(db, user_id, domain)
            if other and other.id != company.id:
                raise Duplicate(
                    f"A company with domain {domain} already exists",
                    details={"existing_company_id": str(other.id)},
                )
            company.normalized_domain = domain
    for k, v in changes.items():
        setattr(company, k, v)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Duplicate("A company with this domain already exists") from exc
    db.refresh(company)
    return company


def delete_company(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> None:
    company = get_company(db, user_id, company_id)
    active = db.scalar(
        select(func.count())
        .select_from(ResearchJob)
        .where(ResearchJob.company_id == company.id, ResearchJob.status.in_([s.value for s in ACTIVE_STATUSES]))
    )
    if active:
        raise Conflict("Research is in progress for this company; cancel it before deleting")
    # Explicit child deletion keeps behaviour identical on every backend.
    for model in (ResearchReport, ResearchFinding, CompanyProfile, SourceDocument, ResearchSource, ResearchJob):
        db.execute(delete(model).where(model.company_id == company.id))
    db.delete(company)
    db.commit()


def dashboard_stats(db: Session, user_id: uuid.UUID) -> dict:
    rows = dict(
        db.execute(
            select(Company.latest_status, func.count()).where(Company.user_id == user_id).group_by(Company.latest_status)
        ).all()
    )
    total = sum(rows.values())
    processing = sum(n for s, n in rows.items() if s in PROCESSING or s == JobStatus.queued.value)
    return {
        "total": total,
        "completed": rows.get(JobStatus.completed.value, 0),
        "processing": processing,
        "failed_or_partial": rows.get(JobStatus.failed.value, 0) + rows.get(JobStatus.partial.value, 0),
        "pending": rows.get(None, 0) + rows.get(JobStatus.cancelled.value, 0),
    }
