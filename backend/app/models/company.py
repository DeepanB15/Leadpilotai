import uuid
from datetime import datetime

from sqlalchemy import Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import UTCDateTime, utcnow


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_domain", name="uq_companies_user_domain"),
        Index("idx_companies_user", "user_id"),
        Index("idx_companies_domain", "normalized_domain"),
        Index("idx_companies_user_status", "user_id", "latest_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    website_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_domain: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    instagram_url: Mapped[str | None] = mapped_column(Text)
    youtube_url: Mapped[str | None] = mapped_column(Text)
    facebook_url: Mapped[str | None] = mapped_column(Text)
    x_url: Mapped[str | None] = mapped_column(Text)
    latest_status: Mapped[str | None] = mapped_column(String(32))
    last_researched_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    def social_urls(self) -> dict[str, str]:
        out = {}
        for p in ("linkedin", "instagram", "youtube", "facebook", "x"):
            v = getattr(self, f"{p}_url")
            if v:
                out[p] = v
        return out
