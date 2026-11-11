# LeadPilotAI v1.0 — API Specification

Base path: `/api/v1` · Format: JSON (except file upload/export) · Auth: Supabase bearer token

## Authentication
- Every endpoint except `GET /health` requires `Authorization: Bearer <supabase_access_token>`.
- Backend verifies the token with Supabase's trusted mechanism (JWKS / JWT secret), extracts the user ID and uses it for all ownership checks.
- A `user_id` in a request body or query is never trusted.
- Accessing another user's resource returns `404` (do not leak existence).

## Conventions
- IDs are UUIDs. Timestamps are ISO 8601 UTC.
- Pagination: `?limit=50&offset=0` (max limit 200). List responses: `{ "items": [...], "total": N }`.
- Errors:
```json
{ "error": { "code": "validation_error", "message": "Invalid website URL", "details": [...], "request_id": "..." } }
```
- Codes: `400 validation_error`, `401 unauthorized`, `404 not_found`, `409 duplicate`, `413 file_too_large`, `422 unprocessable`, `429 rate_limited`, `500 internal_error`.
- Every response includes an `X-Request-ID` header.

## Endpoints

### Health
| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | No auth. `{ "status": "ok", "database": "ok" }` |

### Companies
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/companies` | List. Query: `q`, `status`, `limit`, `offset`, `sort` |
| POST | `/companies` | Create |
| GET | `/companies/{id}` | Get |
| PATCH | `/companies/{id}` | Update |
| DELETE | `/companies/{id}` | Delete (cascades) |

Create request:
```json
{
  "name": "Acme Software",
  "website_url": "acme.com",
  "linkedin_url": "linkedin.com/company/acme",
  "instagram_url": null, "youtube_url": null, "facebook_url": null, "x_url": null,
  "industry": null
}
```
Response `201`: company object including `normalized_domain`, `latest_status`, `last_researched_at`, `created_at`, `updated_at`.
`409 duplicate` returns the existing company ID.

### Imports
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/imports/csv` | multipart `file` (.csv) |
| POST | `/imports/excel` | multipart `file` (.xlsx) |

Query: `?mode=preview` (default) or `?mode=commit`. Preview returns rows without saving; commit saves valid, non-duplicate rows.
```json
{
  "mode": "preview",
  "summary": { "total": 120, "valid": 108, "duplicates": 9, "invalid": 3 },
  "rows": [
    { "row": 2, "status": "valid|duplicate|invalid", "normalized_domain": "acme.com",
      "errors": [], "existing_company_id": null, "data": { } }
  ],
  "created_company_ids": []
}
```
Limits: file size (default 5 MB), row count (default 1,000). Missing required columns -> `400`.

### Research
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/companies/{id}/research` | Start single research |
| POST | `/research/batch` | Start batch research |
| GET | `/research/jobs` | List jobs. Query: `status`, `company_id`, `limit`, `offset` |
| GET | `/research/jobs/{id}` | Job detail with per-source status |
| POST | `/research/jobs/{id}/retry` | Retry `failed`/`partial` job |
| POST | `/research/jobs/{id}/cancel` | Cancel non-terminal job |

Start response `202`:
```json
{ "job_id": "uuid", "company_id": "uuid", "status": "queued", "message": "Research job created successfully" }
```
Batch request: `{ "company_ids": ["uuid", "uuid"] }` (max 100). Response: per-company results, so one invalid company never blocks the others:
```json
{ "jobs": [ { "company_id": "uuid", "job_id": "uuid", "status": "queued" },
            { "company_id": "uuid", "error": "already_in_progress" } ] }
```
Job detail:
```json
{
  "id": "uuid", "company_id": "uuid", "status": "researching",
  "progress_stage": "social_research", "attempt": 1,
  "model_id": null, "pipeline_version": "1.0.0",
  "started_at": "...", "completed_at": null, "error_info": null,
  "sources": [
    { "platform": "website", "access_status": "completed", "documents": 8 },
    { "platform": "linkedin", "access_status": "inaccessible", "status_detail": "Authentication required" },
    { "platform": "youtube", "access_status": "not_discovered" }
  ]
}
```
Starting research while a job is active for that company returns `409`.

### Company research data
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/companies/{id}/sources` | Sources with verification and access status; `?include=documents` adds document list |
| GET | `/companies/{id}/profile` | Latest company profile (`?version=N` optional) |
| GET | `/companies/{id}/findings` | Findings; filters `classification`, `confidence`, `finding_type` |
| GET | `/companies/{id}/reports` | Report list (id, version, created_at) |

Profile response (abridged):
```json
{
  "version": 2, "model_id": "…", "schema_version": "1.0", "prompt_version": "1.0",
  "generated_at": "...",
  "profile_data": {
    "company_overview": { "description": "...", "industry": "Software",
                          "business_model": "B2B SaaS", "target_audience": ["SMB"] },
    "products": [ { "name": "...", "description": "..." } ],
    "services": [],
    "market_positioning": "...",
    "digital_presence": { "website": "...", "social": "..." }
  },
  "fields": [
    { "field": "business_model", "value": "B2B SaaS", "classification": "observed_fact",
      "evidence": [ { "document_id": "uuid", "source_url": "https://…/pricing", "excerpt": "…" } ] }
  ]
}
```
Unsupported fields use `"value": "unknown"` with empty evidence.

Finding object:
```json
{
  "id": "uuid", "finding_type": "opportunity", "classification": "inference",
  "title": "Explore customer-outcome messaging", "description": "...",
  "evidence": [ { "document_id": "uuid", "source_url": "...", "excerpt": "..." } ],
  "confidence": "medium",
  "confidence_factors": { "evidence_quality": "medium", "independent_sources": 2, "recency": "recent", "consistency": "consistent" },
  "review_status": "unreviewed"
}
```

### Reports
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/reports/{id}` | Full report |
| GET | `/reports/{id}/export?format=pdf\|csv` | Download export |

Report shape:
```json
{
  "id": "uuid", "company_id": "uuid", "version": 1, "created_at": "...",
  "overview": { },
  "research_coverage": [ { "platform": "website", "status": "completed", "last_checked_at": "..." } ],
  "findings": [ ],
  "sales_preparation": {
    "talking_points": [ ], "prospect_questions": [ ],
    "value_proposition": "...", "suggested_next_action": "..."
  },
  "limitations": [ "LinkedIn could not be accessed; its presence is not assessed." ],
  "model_id": "…", "prompt_version": "1.0"
}
```
Export responses: `application/pdf` or `text/csv` with `Content-Disposition: attachment`.

## Status and enum values
- Job: `queued, discovering, researching, analyzing, generating_report, completed, partial, failed, cancelled`
- Access: `completed, partial, inaccessible, not_discovered, unsupported, failed`
- Verification: `verified, unverified, rejected`
- Finding classification: `observed_fact, inference, unknown`
- Confidence: `high, medium, low`

## Frontend polling
Poll `GET /research/jobs/{id}` every 3 s while non-terminal, backing off to 10 s after 1 minute. Stop on `completed`, `partial`, `failed`, `cancelled`.

## Rate limits (suggested defaults)
- Research starts: 30/min per user.
- Imports: 5/min per user.
- Outbound crawling is rate-limited per target domain inside the worker, independent of API limits.

---

## Implementation notes (as built in v1.0)

Differences and additions relative to the draft above:

- `GET /dashboard/stats` returns `{total, completed, processing, failed_or_partial, pending}` for the dashboard tiles.
- `GET /companies/export/csv` exports the user's company records.
- `POST /research/jobs/{id}/retry` creates a **new** job for the same company (run history is preserved) and returns its id.
- `POST /research/jobs/{id}/cancel` cancels a queued or running job; a running worker stops at the next stage boundary.
- `GET /reports/{id}` returns the stored report merged with `id`, `company_id`, `job_id`, `version`, `created_at`.
- Import endpoints take `?mode=preview|commit`; commit saves valid, non-duplicate rows only.
- Validation errors use HTTP 400 with `error.code = "validation_error"`.
- Starting research while a job is active returns 409 with `error.code = "already_in_progress"`; in a batch the same condition is reported per company.
- Jobs list/detail include `company_name` and per-source status; platforms with no source row are reported as `not_discovered` once the job has finished.
- Sales preparation items are `{text, based_on_findings: [finding_id]}`; ungrounded items are dropped.
