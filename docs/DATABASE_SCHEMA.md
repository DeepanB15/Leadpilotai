# LeadPilotAI v1.0 — Database Schema

Database: Supabase PostgreSQL · ORM: SQLAlchemy · Migrations: Alembic · Auth: Supabase Auth (`auth.users`)

## Conventions
- UUID primary keys (`gen_random_uuid()`), timestamps `TIMESTAMPTZ` in UTC.
- `user_id` references `auth.users(id)`; no custom password or auth tables.
- JSONB only for variable research output; relational fields stay relational.
- Service-role credentials are backend-only. RLS enabled on every table.

## Relationships

```
auth.users 1:N companies
companies  1:N research_jobs
companies  1:N research_sources
research_sources 1:N source_documents
companies  1:N company_profiles (versioned)
companies  1:N research_findings
companies  1:N research_reports (versioned)
research_jobs 1:N (sources, profiles, findings, reports via job_id)
```

## Enums

```sql
CREATE TYPE job_status AS ENUM (
  'queued','discovering','researching','analyzing','generating_report',
  'completed','partial','failed','cancelled');

CREATE TYPE source_type AS ENUM ('website','social');
CREATE TYPE platform AS ENUM ('website','linkedin','instagram','youtube','facebook','x');

CREATE TYPE verification_status AS ENUM ('verified','unverified','rejected');

CREATE TYPE access_status AS ENUM (
  'completed','partial','inaccessible','not_discovered','unsupported','failed');

CREATE TYPE finding_class AS ENUM ('observed_fact','inference','unknown');
CREATE TYPE confidence_label AS ENUM ('high','medium','low');
CREATE TYPE review_status AS ENUM ('unreviewed','accepted','rejected');
```

## Tables

### companies
```sql
CREATE TABLE companies (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  website_url       TEXT NOT NULL,
  normalized_domain TEXT NOT NULL,
  industry          TEXT,
  linkedin_url      TEXT,
  instagram_url     TEXT,
  youtube_url       TEXT,
  facebook_url      TEXT,
  x_url             TEXT,
  latest_status     job_status,            -- denormalized for dashboard filtering
  last_researched_at TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, normalized_domain)      -- duplicate detection per user
);
CREATE INDEX idx_companies_user ON companies(user_id);
CREATE INDEX idx_companies_domain ON companies(normalized_domain);
CREATE INDEX idx_companies_user_status ON companies(user_id, latest_status);
```

### research_jobs
```sql
CREATE TABLE research_jobs (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  job_type         TEXT NOT NULL DEFAULT 'full_research',
  status           job_status NOT NULL DEFAULT 'queued',
  progress_stage   TEXT,
  attempt          INT NOT NULL DEFAULT 0,
  error_info       JSONB,
  model_id         TEXT,                  -- e.g. Ollama model tag
  pipeline_version TEXT,
  locked_by        TEXT,                  -- worker identity (lease)
  lease_expires_at TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at       TIMESTAMPTZ,
  completed_at     TIMESTAMPTZ
);
CREATE INDEX idx_jobs_company ON research_jobs(company_id);
CREATE INDEX idx_jobs_user_status ON research_jobs(user_id, status);
CREATE INDEX idx_jobs_claim ON research_jobs(status, lease_expires_at);
```

Atomic claim pattern for the worker:
```sql
UPDATE research_jobs SET status='discovering', locked_by=$1,
       lease_expires_at=now()+interval '5 minutes', started_at=COALESCE(started_at,now())
WHERE id = (
  SELECT id FROM research_jobs
  WHERE (status='queued' OR (status IN ('discovering','researching','analyzing','generating_report')
         AND lease_expires_at < now()))
  ORDER BY created_at
  FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING *;
```

### research_sources
```sql
CREATE TABLE research_sources (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id          UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  job_id              UUID REFERENCES research_jobs(id) ON DELETE SET NULL,
  user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  source_type         source_type NOT NULL,
  platform            platform NOT NULL,
  source_url          TEXT NOT NULL,
  discovery_method    TEXT,               -- website_link | user_supplied | search_provider
  verification_status verification_status NOT NULL DEFAULT 'unverified',
  access_status       access_status NOT NULL,
  status_detail       TEXT,
  profile_metadata    JSONB,
  last_checked_at     TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, platform, source_url)
);
CREATE INDEX idx_sources_company ON research_sources(company_id);
```

### source_documents
```sql
CREATE TABLE source_documents (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id     UUID NOT NULL REFERENCES research_sources(id) ON DELETE CASCADE,
  company_id    UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  document_type TEXT NOT NULL,            -- homepage, about_page, product_page, post, video, ...
  url           TEXT NOT NULL,
  title         TEXT,
  content       TEXT NOT NULL,
  content_hash  TEXT NOT NULL,
  published_at  TIMESTAMPTZ,
  collected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata      JSONB NOT NULL DEFAULT '{}',  -- http_status, extraction_method, ...
  UNIQUE (source_id, content_hash)
);
CREATE INDEX idx_docs_company ON source_documents(company_id);
CREATE INDEX idx_docs_source ON source_documents(source_id);
```

### company_profiles
```sql
CREATE TABLE company_profiles (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  job_id         UUID REFERENCES research_jobs(id) ON DELETE SET NULL,
  user_id        UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  version        INT NOT NULL,
  profile_data   JSONB NOT NULL,          -- validated against versioned Pydantic schema
  evidence_refs  JSONB NOT NULL DEFAULT '[]',
  model_id       TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  generated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, version)
);
```

### research_findings
```sql
CREATE TABLE research_findings (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  job_id            UUID REFERENCES research_jobs(id) ON DELETE SET NULL,
  user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  finding_type      TEXT NOT NULL,        -- characteristic, strength, digital_presence, content_theme, opportunity, ...
  classification    finding_class NOT NULL,
  title             TEXT NOT NULL,
  description       TEXT NOT NULL,
  evidence          JSONB NOT NULL DEFAULT '[]',  -- [{document_id, source_url, excerpt}]
  confidence        confidence_label NOT NULL,
  confidence_factors JSONB NOT NULL DEFAULT '{}', -- explains deterministic score
  review_status     review_status NOT NULL DEFAULT 'unreviewed',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (classification = 'unknown' OR jsonb_array_length(evidence) > 0)
);
CREATE INDEX idx_findings_company ON research_findings(company_id);
```

### research_reports
```sql
CREATE TABLE research_reports (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  job_id           UUID REFERENCES research_jobs(id) ON DELETE SET NULL,
  user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  version          INT NOT NULL,
  report_data      JSONB NOT NULL,        -- overview, coverage, findings, sales prep, limitations
  export_ref       TEXT,                  -- storage path for generated PDF
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, version)
);
```

## Row Level Security

Enable on all tables. Frontend/anon access uses the user's JWT; the backend additionally filters by the verified user ID.

```sql
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
CREATE POLICY companies_owner ON companies
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
-- Repeat the same pattern for research_jobs, research_sources, source_documents,
-- company_profiles, research_findings, research_reports (all carry user_id).
```

The worker uses the backend service role (bypasses RLS) and must always scope writes to the job's `user_id`/`company_id`.

## Data rules
1. Every user-owned record carries `user_id`; ownership enforced in queries and RLS.
2. Domains are normalized (lowercase, strip scheme/`www`/path) before uniqueness checks.
3. Findings that are not `unknown` must have at least one evidence reference (DB check + app validation).
4. Evidence `document_id`s must exist and belong to the same company (validated before insert).
5. Profiles and reports are append-only and versioned; history is retained.
6. Deleting a company cascades to all research data.
