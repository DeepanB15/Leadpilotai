import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobCreated(BaseModel):
    job_id: uuid.UUID
    company_id: uuid.UUID
    status: str
    message: str = "Research job created successfully"


class BatchRequest(BaseModel):
    company_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class BatchItem(BaseModel):
    company_id: uuid.UUID
    job_id: uuid.UUID | None = None
    status: str | None = None
    error: str | None = None


class BatchResponse(BaseModel):
    jobs: list[BatchItem]


class SourceStatus(BaseModel):
    platform: str
    source_url: str | None = None
    access_status: str
    verification_status: str | None = None
    status_detail: str | None = None
    documents: int = 0


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    company_name: str | None = None
    job_type: str
    status: str
    progress_stage: str | None = None
    attempt: int
    error_info: dict | None = None
    model_id: str | None = None
    pipeline_version: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    sources: list[SourceStatus] = []


class JobList(BaseModel):
    items: list[JobOut]
    total: int


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_type: str
    url: str
    title: str | None = None
    content: str
    published_at: datetime | None = None
    collected_at: datetime
    meta: dict = Field(default_factory=dict, serialization_alias="metadata")


class SourceOut(BaseModel):
    id: uuid.UUID
    platform: str
    source_type: str
    source_url: str
    discovery_method: str | None = None
    verification_status: str
    access_status: str
    status_detail: str | None = None
    profile_metadata: dict | None = None
    last_checked_at: datetime | None = None
    document_count: int = 0
    documents: list[DocumentOut] | None = None


class SourceList(BaseModel):
    items: list[SourceOut]
    coverage: list[dict[str, Any]]


class ProfileOut(BaseModel):
    version: int
    model_id: str
    schema_version: str
    prompt_version: str
    generated_at: datetime
    profile_data: dict
    fields: list[dict]


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_type: str
    classification: str
    title: str
    description: str
    evidence: list[dict]
    confidence: str
    confidence_factors: dict
    review_status: str
    created_at: datetime


class FindingList(BaseModel):
    items: list[FindingOut]
    total: int


class ReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    created_at: datetime
    job_id: uuid.UUID | None = None


class ReportSummaryList(BaseModel):
    items: list[ReportSummary]
    total: int


class ReportOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    version: int
    created_at: datetime
    job_id: uuid.UUID | None = None
    # remaining report keys (overview, research_coverage, findings, ...) are merged in by the API
    model_config = ConfigDict(extra="allow")
