import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.urls import InvalidURL, normalize_website, validate_social_field

SOCIAL_FIELDS = ("linkedin", "instagram", "youtube", "facebook", "x")


def _check_name(v: str) -> str:
    v = " ".join((v or "").split())
    if not v:
        raise ValueError("Company name is required")
    if len(v) > 200:
        raise ValueError("Company name must be at most 200 characters")
    return v


def _check_website(v: str) -> str:
    try:
        return normalize_website(v).url
    except InvalidURL as exc:
        raise ValueError(str(exc)) from exc


class _SocialMixin(BaseModel):
    linkedin_url: str | None = None
    instagram_url: str | None = None
    youtube_url: str | None = None
    facebook_url: str | None = None
    x_url: str | None = None

    @model_validator(mode="after")
    def _validate_socials(self):
        for p in SOCIAL_FIELDS:
            field = f"{p}_url"
            val = getattr(self, field)
            if val is None or not str(val).strip():
                setattr(self, field, None)
                continue
            try:
                setattr(self, field, validate_social_field(p, val))
            except InvalidURL as exc:
                raise ValueError(f"{field}: {exc}") from exc
        return self


class CompanyCreate(_SocialMixin):
    name: str
    website_url: str
    industry: str | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return _check_name(v)

    @field_validator("website_url")
    @classmethod
    def _site(cls, v):
        return _check_website(v)

    @field_validator("industry")
    @classmethod
    def _industry(cls, v):
        v = (v or "").strip()
        return v or None


class CompanyUpdate(_SocialMixin):
    # Only explicitly-sent fields are applied (see service: model_fields_set).
    name: str | None = None
    website_url: str | None = None
    industry: str | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return None if v is None else _check_name(v)

    @field_validator("website_url")
    @classmethod
    def _site(cls, v):
        return None if v is None else _check_website(v)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    website_url: str
    normalized_domain: str
    industry: str | None = None
    linkedin_url: str | None = None
    instagram_url: str | None = None
    youtube_url: str | None = None
    facebook_url: str | None = None
    x_url: str | None = None
    latest_status: str | None = None
    last_researched_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    platforms: list[str] = []


class CompanyList(BaseModel):
    items: list[CompanyOut]
    total: int


class DashboardStats(BaseModel):
    total: int
    completed: int
    processing: int
    failed_or_partial: int
    pending: int
