from datetime import timedelta

from app.core.config import get_settings
from app.enums import JobStatus
from app.models import Company, ResearchJob
from app.services import job_service
from app.utils.time import utcnow
from tests.conftest import USER_A

S = get_settings()


def mk_company(db, domain="a.com"):
    c = Company(user_id=USER_A, name=domain, website_url=f"https://{domain}", normalized_domain=domain)
    db.add(c)
    db.commit()
    return c


def test_claim_is_exclusive_and_fifo(db):
    c1, c2 = mk_company(db, "a.com"), mk_company(db, "b.com")
    j1 = job_service.create_job(db, c1, S)
    j2 = job_service.create_job(db, c2, S)
    claimed = job_service.claim_next_job(db, "w1", S)
    assert claimed.id == j1.id and claimed.status == "discovering" and claimed.attempt == 1 and claimed.locked_by == "w1"
    assert job_service.claim_next_job(db, "w2", S).id == j2.id
    assert job_service.claim_next_job(db, "w3", S) is None  # both leased


def test_abandoned_job_is_recovered_after_lease_expiry(db):
    c = mk_company(db)
    job = job_service.create_job(db, c, S)
    job_service.claim_next_job(db, "dead-worker", S)
    assert job_service.claim_next_job(db, "w2", S) is None  # lease still valid
    job.lease_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    again = job_service.claim_next_job(db, "w2", S)
    assert again.id == job.id and again.attempt == 2 and again.locked_by == "w2"


def test_job_fails_after_max_attempts(db):
    c = mk_company(db)
    job = job_service.create_job(db, c, S)
    job.status, job.attempt, job.lease_expires_at = "researching", S.job_max_attempts, utcnow() - timedelta(seconds=5)
    db.commit()
    assert job_service.claim_next_job(db, "w", S) is None
    db.refresh(job), db.refresh(c)
    assert job.status == "failed" and c.latest_status == "failed" and "abandoned" in job.error_info["error"]


def test_cancelled_jobs_are_not_claimed_and_stage_updates_honour_cancel(db):
    c = mk_company(db)
    job = job_service.create_job(db, c, S)
    job_service.cancel_job(db, job)
    assert job_service.claim_next_job(db, "w", S) is None
    try:
        job_service.set_stage(db, job, JobStatus.researching, "x", S)
        raise AssertionError("expected JobCancelled")
    except job_service.JobCancelled:
        pass
    job_service.finish_job(db, job, JobStatus.completed)  # must not overwrite cancellation
    db.refresh(job)
    assert job.status == "cancelled"
