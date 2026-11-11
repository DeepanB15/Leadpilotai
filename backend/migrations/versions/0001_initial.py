"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.types import JSONType, UTCDateTime

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

OWNED_TABLES = [
    "companies",
    "research_jobs",
    "research_sources",
    "source_documents",
    "company_profiles",
    "research_findings",
    "research_reports",
]


def _pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        sa.Uuid(),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()") if _pg() else None,
    )


def _now():
    return sa.func.now() if _pg() else None


def _created(name="created_at"):
    return sa.Column(name, UTCDateTime(), nullable=False, server_default=_now())


def upgrade() -> None:
    pg = _pg()
    auth_users_exists = False
    if pg:
        bind = op.get_bind()
        auth_users_exists = bool(bind.execute(sa.text("SELECT to_regclass('auth.users') IS NOT NULL")).scalar())
        # Local plain-Postgres development: provide auth.uid() if Supabase's is absent.
        op.execute("CREATE SCHEMA IF NOT EXISTS auth")
        if not bind.execute(sa.text("SELECT to_regprocedure('auth.uid()') IS NOT NULL")).scalar():
            op.execute(
                "CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS "
                "$$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$"
            )

    op.create_table(
        "companies",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=False),
        sa.Column("normalized_domain", sa.Text(), nullable=False),
        sa.Column("industry", sa.Text()),
        sa.Column("linkedin_url", sa.Text()),
        sa.Column("instagram_url", sa.Text()),
        sa.Column("youtube_url", sa.Text()),
        sa.Column("facebook_url", sa.Text()),
        sa.Column("x_url", sa.Text()),
        sa.Column("latest_status", sa.String(32)),
        sa.Column("last_researched_at", UTCDateTime()),
        _created("created_at"),
        _created("updated_at"),
        sa.UniqueConstraint("user_id", "normalized_domain", name="uq_companies_user_domain"),
    )
    op.create_index("idx_companies_user", "companies", ["user_id"])
    op.create_index("idx_companies_domain", "companies", ["normalized_domain"])
    op.create_index("idx_companies_user_status", "companies", ["user_id", "latest_status"])

    op.create_table(
        "research_jobs",
        _uuid_pk(),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False, server_default="full_research"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("progress_stage", sa.Text()),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_info", JSONType),
        sa.Column("model_id", sa.Text()),
        sa.Column("pipeline_version", sa.Text()),
        sa.Column("locked_by", sa.Text()),
        sa.Column("lease_expires_at", UTCDateTime()),
        _created("created_at"),
        sa.Column("started_at", UTCDateTime()),
        sa.Column("completed_at", UTCDateTime()),
    )
    op.create_index("idx_jobs_company", "research_jobs", ["company_id"])
    op.create_index("idx_jobs_user_status", "research_jobs", ["user_id", "status"])
    op.create_index("idx_jobs_claim", "research_jobs", ["status", "lease_expires_at"])

    op.create_table(
        "research_sources",
        _uuid_pk(),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("research_jobs.id", ondelete="SET NULL")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("discovery_method", sa.Text()),
        sa.Column("verification_status", sa.String(16), nullable=False, server_default="unverified"),
        sa.Column("access_status", sa.String(16), nullable=False, server_default="failed"),
        sa.Column("status_detail", sa.Text()),
        sa.Column("profile_metadata", JSONType),
        sa.Column("last_checked_at", UTCDateTime()),
        _created("created_at"),
        sa.UniqueConstraint("company_id", "platform", "source_url", name="uq_sources_company_platform_url"),
    )
    op.create_index("idx_sources_company", "research_sources", ["company_id"])

    op.create_table(
        "source_documents",
        _uuid_pk(),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("published_at", UTCDateTime()),
        _created("collected_at"),
        sa.Column("metadata", JSONType, nullable=False, server_default=sa.text("'{}'")),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_docs_source_hash"),
    )
    op.create_index("idx_docs_company", "source_documents", ["company_id"])
    op.create_index("idx_docs_source", "source_documents", ["source_id"])

    op.create_table(
        "company_profiles",
        _uuid_pk(),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("research_jobs.id", ondelete="SET NULL")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("profile_data", JSONType, nullable=False),
        sa.Column("evidence_refs", JSONType, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        _created("generated_at"),
        sa.UniqueConstraint("company_id", "version", name="uq_profiles_company_version"),
    )

    op.create_table(
        "research_findings",
        _uuid_pk(),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("research_jobs.id", ondelete="SET NULL")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("finding_type", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", JSONType, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("confidence", sa.String(8), nullable=False),
        sa.Column("confidence_factors", JSONType, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="unreviewed"),
        _created("created_at"),
    )
    op.create_index("idx_findings_company", "research_findings", ["company_id"])

    op.create_table(
        "research_reports",
        _uuid_pk(),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("research_jobs.id", ondelete="SET NULL")),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("report_data", JSONType, nullable=False),
        sa.Column("export_ref", sa.Text()),
        _created("created_at"),
        sa.UniqueConstraint("company_id", "version", name="uq_reports_company_version"),
    )

    if pg:
        # Enforced vocabularies
        op.execute(
            "ALTER TABLE research_jobs ADD CONSTRAINT ck_jobs_status CHECK (status IN "
            "('queued','discovering','researching','analyzing','generating_report',"
            "'completed','partial','failed','cancelled'))"
        )
        op.execute(
            "ALTER TABLE research_sources ADD CONSTRAINT ck_sources_access CHECK (access_status IN "
            "('completed','partial','inaccessible','not_discovered','unsupported','failed'))"
        )
        op.execute(
            "ALTER TABLE research_sources ADD CONSTRAINT ck_sources_verification CHECK "
            "(verification_status IN ('verified','unverified','rejected'))"
        )
        op.execute(
            "ALTER TABLE research_findings ADD CONSTRAINT ck_findings_class CHECK "
            "(classification IN ('observed_fact','inference','unknown'))"
        )
        op.execute(
            "ALTER TABLE research_findings ADD CONSTRAINT ck_findings_confidence CHECK "
            "(confidence IN ('high','medium','low'))"
        )
        # Every non-unknown finding must carry evidence
        op.execute(
            "ALTER TABLE research_findings ADD CONSTRAINT ck_findings_evidence CHECK "
            "(classification = 'unknown' OR jsonb_array_length(evidence) > 0)"
        )
        op.execute(
            "ALTER TABLE research_jobs ADD CONSTRAINT ck_jobs_attempt CHECK (attempt >= 0)"
        )
        # Ownership: reference Supabase auth users when the real table exists.
        if auth_users_exists:
            for t in OWNED_TABLES:
                op.execute(
                    f"ALTER TABLE {t} ADD CONSTRAINT fk_{t}_user FOREIGN KEY (user_id) "
                    f"REFERENCES auth.users(id) ON DELETE CASCADE"
                )
        # Row Level Security
        for t in OWNED_TABLES:
            op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {t}_owner ON {t} FOR ALL "
                f"USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())"
            )


def downgrade() -> None:
    for t in reversed(OWNED_TABLES):
        op.drop_table(t)
