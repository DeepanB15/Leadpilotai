import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import JobStatus
from app.models.types import JSONType, UTCDateTime, utcnow


class ResearchJob(Base):
    __tablename__ = "research_jobs"
    __table_args__ = (
        Index("idx_jobs_company", "company_id"),
        Index("idx_jobs_user_status", "user_id", "status"),
        Index("idx_jobs_claim", "status", "lease_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    job_type: Mapped[str] = mapped_column(Text, nullable=False, default="full_research")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JobStatus.queued.value)
    progress_stage: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_info: Mapped[dict | None] = mapped_column(JSONType)
    model_id: Mapped[str | None] = mapped_column(Text)
    pipeline_version: Mapped[str | None] = mapped_column(Text)
    locked_by: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
