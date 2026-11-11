import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import ReviewStatus
from app.models.types import JSONType, UTCDateTime, utcnow


class ResearchFinding(Base):
    __tablename__ = "research_findings"
    __table_args__ = (Index("idx_findings_company", "company_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("research_jobs.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    finding_type: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)
    confidence_factors: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default=ReviewStatus.unreviewed.value)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
