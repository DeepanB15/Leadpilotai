import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthUser, get_current_user, get_db
from app.core.config import get_settings
from app.core.errors import AppError
from app.enums import ALL_PLATFORMS, AccessStatus
from app.models import Company, ResearchJob, ResearchSource, SourceDocument
from app.schemas.research import BatchItem, BatchRequest, BatchResponse, JobCreated, JobList, JobOut, SourceStatus
from app.services import company_service, job_service
from app.services.rate_limit import check_rate_limit

router = APIRouter(tags=["research"])


def _job_out(db: Session, job: ResearchJob, company_name: str | None) -> JobOut:
    sources = list(
        db.scalars(
            select(ResearchSource).where(ResearchSource.company_id == job.company_id, ResearchSource.job_id == job.id)
        )
    )
    counts = dict(
        db.execute(
            select(SourceDocument.source_id, func.count())
            .where(SourceDocument.company_id == job.company_id)
            .group_by(SourceDocument.source_id)
        ).all()
    )
    by_platform = {s.platform: s for s in sources}
    statuses: list[SourceStatus] = []
    for p in ALL_PLATFORMS:
        s = by_platform.get(p.value)
        if s:
            statuses.append(
                SourceStatus(
                    platform=s.platform,
                    source_url=s.source_url,
                    access_status=s.access_status,
                    verification_status=s.verification_status,
                    status_detail=s.status_detail,
                    documents=counts.get(s.id, 0),
                )
            )
        elif job.status in ("completed", "partial", "failed"):
            statuses.append(SourceStatus(platform=p.value, access_status=AccessStatus.not_discovered.value))
    out = JobOut.model_validate(job)
    out.company_name = company_name
    out.sources = statuses
    return out


def _start(db: Session, user: AuthUser, company_id: uuid.UUID) -> ResearchJob:
    company = company_service.get_company(db, user.id, company_id)
    return job_service.create_job(db, company, get_settings())


@router.post("/companies/{company_id}/research", response_model=JobCreated, status_code=202)
def start_research(company_id: uuid.UUID, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    check_rate_limit(str(user.id), "research", get_settings().rate_limit_research_per_min)
    job = _start(db, user, company_id)
    return JobCreated(job_id=job.id, company_id=job.company_id, status=job.status)


@router.post("/research/batch", response_model=BatchResponse, status_code=202)
def start_batch(req: BatchRequest, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    check_rate_limit(str(user.id), "research", get_settings().rate_limit_research_per_min * 2)
    results: list[BatchItem] = []
    for cid in dict.fromkeys(req.company_ids):
        try:
            job = _start(db, user, cid)
            results.append(BatchItem(company_id=cid, job_id=job.id, status=job.status))
        except AppError as exc:  # one invalid company never blocks the others
            db.rollback()
            results.append(BatchItem(company_id=cid, error=exc.code if exc.code != "conflict" else "already_in_progress"))
    return BatchResponse(jobs=results)


@router.get("/research/jobs", response_model=JobList)
def list_jobs(
    status: str | None = Query(None, max_length=32),
    company_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(ResearchJob, Company.name).join(Company, Company.id == ResearchJob.company_id)
    stmt = stmt.where(ResearchJob.user_id == user.id)
    if status:
        stmt = stmt.where(ResearchJob.status == status)
    if company_id:
        stmt = stmt.where(ResearchJob.company_id == company_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(ResearchJob.created_at.desc()).limit(limit).offset(offset)).all()
    return JobList(items=[_job_out(db, job, name) for job, name in rows], total=total)


@router.get("/research/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    job = job_service.get_job(db, user.id, job_id)
    company = db.get(Company, job.company_id)
    return _job_out(db, job, company.name if company else None)


@router.post("/research/jobs/{job_id}/retry", response_model=JobCreated, status_code=202)
def retry_job(job_id: uuid.UUID, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    check_rate_limit(str(user.id), "research", get_settings().rate_limit_research_per_min)
    job = job_service.get_job(db, user.id, job_id)
    new_job = job_service.retry_job(db, job, get_settings())
    return JobCreated(job_id=new_job.id, company_id=new_job.company_id, status=new_job.status, message="Retry job created")


@router.post("/research/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: uuid.UUID, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    job = job_service.cancel_job(db, job_service.get_job(db, user.id, job_id))
    company = db.get(Company, job.company_id)
    return _job_out(db, job, company.name if company else None)
