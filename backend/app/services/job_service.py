"""Research job lifecycle: creation, atomic claiming with leases, stage updates, cancel/retry."""

import uuid
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import Conflict, NotFound
from app.enums import ACTIVE_STATUSES, RUNNING_STATUSES, JobStatus
from app.models import Company, ResearchJob
from app.utils.time import utcnow

ACTIVE_VALUES = [s.value for s in ACTIVE_STATUSES]
RUNNING_VALUES = [s.value for s in RUNNING_STATUSES]


class JobCancelled(Exception):
    pass


def create_job(db: Session, company: Company, settings: Settings, job_type: str = "full_research") -> ResearchJob:
    active = db.scalar(
        select(func.count())
        .select_from(ResearchJob)
        .where(ResearchJob.company_id == company.id, ResearchJob.status.in_(ACTIVE_VALUES))
    )
    if active:
        raise Conflict("A research job is already in progress for this company", code="already_in_progress")
    job = ResearchJob(
        company_id=company.id,
        user_id=company.user_id,
        job_type=job_type,
        status=JobStatus.queued.value,
        pipeline_version=settings.pipeline_version,
    )
    db.add(job)
    company.latest_status = JobStatus.queued.value
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> ResearchJob:
    job = db.scalar(select(ResearchJob).where(ResearchJob.id == job_id, ResearchJob.user_id == user_id))
    if not job:
        raise NotFound("Research job not found")
    return job


def cancel_job(db: Session, job: ResearchJob) -> ResearchJob:
    if job.status not in ACTIVE_VALUES:
        raise Conflict("Only queued or running jobs can be cancelled")
    job.status = JobStatus.cancelled.value
    job.completed_at = utcnow()
    job.lease_expires_at = None
    company = db.get(Company, job.company_id)
    if company:
        company.latest_status = JobStatus.cancelled.value
    db.commit()
    db.refresh(job)
    return job


def retry_job(db: Session, job: ResearchJob, settings: Settings) -> ResearchJob:
    if job.status not in (JobStatus.failed.value, JobStatus.partial.value, JobStatus.cancelled.value):
        raise Conflict("Only failed, partial or cancelled jobs can be retried")
    company = db.get(Company, job.company_id)
    if not company:
        raise NotFound("Company not found")
    return create_job(db, company, settings, job.job_type)


def claim_next_job(db: Session, worker_id: str, settings: Settings) -> ResearchJob | None:
    """Atomically claim one runnable job (queued, or running with an expired lease)."""
    now = utcnow()
    stmt = (
        select(ResearchJob)
        .where(
            or_(
                ResearchJob.status == JobStatus.queued.value,
                and_(ResearchJob.status.in_(RUNNING_VALUES), ResearchJob.lease_expires_at < now),
            )
        )
        .order_by(ResearchJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.scalars(stmt).first()
    if job is None:
        db.rollback()
        return None

    company = db.get(Company, job.company_id)
    was_stale = job.status != JobStatus.queued.value
    if was_stale and job.attempt >= settings.job_max_attempts:
        job.status = JobStatus.failed.value
        job.completed_at = now
        job.lease_expires_at = None
        job.error_info = {"error": "Job was abandoned by workers too many times", "attempts": job.attempt}
        if company:
            company.latest_status = JobStatus.failed.value
        db.commit()
        return None

    job.status = JobStatus.discovering.value
    job.progress_stage = "claimed"
    job.attempt += 1
    job.locked_by = worker_id
    job.lease_expires_at = now + timedelta(seconds=settings.job_lease_seconds)
    job.started_at = job.started_at or now
    if company:
        company.latest_status = JobStatus.discovering.value
    db.commit()
    db.refresh(job)
    return job


def set_stage(db: Session, job: ResearchJob, status: JobStatus, stage: str, settings: Settings) -> None:
    """Advance the job, renew the lease, and honour cancellation."""
    db.refresh(job)
    if job.status == JobStatus.cancelled.value:
        raise JobCancelled()
    job.status = status.value
    job.progress_stage = stage
    job.lease_expires_at = utcnow() + timedelta(seconds=settings.job_lease_seconds)
    company = db.get(Company, job.company_id)
    if company:
        company.latest_status = status.value
    db.commit()


def finish_job(
    db: Session, job: ResearchJob, status: JobStatus, *, error_info: dict | None = None, model_id: str | None = None
) -> None:
    db.refresh(job)
    if job.status == JobStatus.cancelled.value:
        return
    job.status = status.value
    job.progress_stage = "done"
    job.completed_at = utcnow()
    job.lease_expires_at = None
    if error_info is not None:
        job.error_info = error_info
    if model_id:
        job.model_id = model_id
    company = db.get(Company, job.company_id)
    if company:
        company.latest_status = status.value
        if status in (JobStatus.completed, JobStatus.partial):
            company.last_researched_at = job.completed_at
    db.commit()
