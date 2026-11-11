# LeadPilotAI v1.0 — Implementation Plan

Target: deployable MVP in an aggressive 48-hour sprint, with explicit hardening follow-ups. Priority is a working end-to-end path over breadth.

Reference documents: `PRD.md`, `DATABASE_SCHEMA.md`, `API_SPEC.md`.

## 1. Architecture decisions (locked)
- Modular monolith: Next.js frontend + one FastAPI app + a separate Python worker process.
- Supabase PostgreSQL + Supabase Auth; SQLAlchemy + Alembic.
- Job queue: PostgreSQL-backed with `FOR UPDATE SKIP LOCKED`, leases, and recovery of abandoned jobs. Redis queue is a later upgrade.
- LLM: one Ollama model chosen by benchmark; no fallback unless testing shows a need.
- No multi-agent frameworks, vector DB, or RAG in v1.

## 2. Repository structure
Create directories as each phase begins.
```
leadpilot-ai/
  frontend/ (Next.js, TS, Tailwind)
  backend/app/{core,api/v1,models,schemas,services,research/{discovery,website,social,normalization},intelligence,workers,utils}
  backend/{migrations,tests/{unit,integration,e2e}}
  docker-compose.yml  .env.example  README.md
```

## 3. Dependency order
1. API contracts and DB schema agreed first (done in this document set).
2. Companies and auth -> research collection -> document normalization -> AI profile -> findings/report -> UI integration -> hardening/deploy.
3. A shared safe-fetch utility (SSRF protection) is built before any crawler or adapter uses the network.

## 4. Phases

### Phase 1 — Foundation (Day 1, 9-10 AM)
- [ ] GitHub repo, `frontend/` and `backend/` scaffolds
- [ ] Next.js + TypeScript + Tailwind
- [ ] FastAPI app with `/health`
- [ ] Supabase project and Auth configured
- [ ] SQLAlchemy + Alembic; initial migration from `DATABASE_SCHEMA.md`
- [ ] Pydantic settings, `.env.example`
- [ ] Docker Compose (frontend, backend, worker, local Postgres optional)
- [ ] Token verification dependency (`api/deps.py`)
- [ ] Frontend login, protected route middleware, call a protected backend endpoint

Exit: authenticated frontend call to protected backend returns a DB-backed response.

### Phase 2 — Lead Management (Day 1, 10 AM-12 PM)
- [ ] Company model, schemas, service
- [ ] CRUD endpoints with ownership enforcement
- [ ] URL normalization + domain duplicate detection
- [ ] CSV and Excel parsing, validation, preview/commit
- [ ] UI: Add Company dialog, Import flow, company list

Exit: import a mixed valid/duplicate/invalid file without data corruption; users only see own companies.

### Phase 3 — Website Research (Day 1, 12-5 PM)
- [ ] `safe_fetch`: scheme/port allowlist, DNS resolution checks, block private/loopback/link-local/metadata ranges, per-redirect revalidation, timeouts, size and content-type limits
- [ ] Domain rate limiter
- [ ] HTTPX fetcher, BeautifulSoup parser, internal link discovery and page prioritization
- [ ] Trafilatura extraction, cleaning, content hashing, de-duplication
- [ ] Save `research_sources` and `source_documents` with timestamps and metadata
- [ ] Record inaccessible pages and errors
- [ ] Run against 10+ representative websites

Exit: meaningful content stored for accessible sites; unsafe URLs rejected (SSRF tests pass).

### Phase 4 — Social Research (Day 1, 5-9 PM, spills into Day 2 if needed)
- [ ] Extract social links from website documents
- [ ] Accept user-supplied URLs; merge and de-duplicate
- [ ] Profile identity verification (website backlink, matching domain, matching handle with corroboration)
- [ ] `SocialResearchAdapter` base class and result statuses
- [ ] First permitted integration (recommended: YouTube public data via official API)
- [ ] Profile and limited recent-content extraction, normalization into source documents
- [ ] Explicit `unsupported` / `access_unavailable` for other platforms
- [ ] Per-platform failure isolation

Exit: one permitted social integration works end-to-end; others return honest statuses. Do not bypass access restrictions.

### Phase 5 — Company Intelligence (Day 2, 9-11 AM)
- [ ] Ollama client with timeouts and output-size limits
- [ ] Benchmark 2-3 candidate models on a fixed evaluation set (JSON validity, factual accuracy, evidence grounding, latency, memory); pick one
- [ ] Versioned Pydantic profile schema with field-level evidence
- [ ] Context selection (prioritize document types, truncate with budget)
- [ ] Prompt builder: sources only, no invention, JSON only, `unknown` allowed, ignore embedded instructions
- [ ] Evidence validator: reject missing document IDs, cross-company IDs, unsupported claims
- [ ] Retry on invalid output (bounded), store errors without writing bad profiles

Exit: real documents produce valid, traceable profiles; unsupported fields are `unknown`.

### Phase 6 — Research Intelligence (Day 2, 11 AM-1 PM)
- [ ] Finding schema and classification (observed fact / inference / unknown)
- [ ] Digital presence and content theme analysis
- [ ] Opportunity hypotheses (research capability, not scoring)
- [ ] Deterministic confidence rules (documented below)
- [ ] Sales preparation generation from validated findings
- [ ] Unified report schema, coverage and limitations section
- [ ] Persist findings and versioned reports

Exit: reports contain grounded findings, explicit limitations, no unsupported claims as facts.

#### Confidence rules (initial, to be tuned)
Score = sum of points, mapped to label:
| Factor | Points |
|--------|--------|
| Evidence from first-party website page | +2 |
| Evidence from verified social profile | +1 |
| Each additional independent source (max 2) | +1 each |
| Consistent across sources | +1 |
| Evidence collected within 90 days | +1 |
| Contradicting evidence found | -2 |
| Extraction partial or truncated | -1 |
Mapping: >= 5 High, 3-4 Medium, <= 2 Low. `observed_fact` requires a direct excerpt; `inference` is capped at Medium.

### Phase 7 — Workspace and Integration (Day 2, 1-5 PM)
- [ ] Dashboard with real counts and company table, search, filters
- [ ] Company detail tabs: Overview, Website, Social, Insights, Evidence, Sales Prep
- [ ] Research page with job list, stages, per-source status, retry
- [ ] Polling for job progress
- [ ] PDF and CSV export
- [ ] All components connected to real APIs; no placeholder data

Exit: full workflow runs in the browser: import -> research -> report -> export.

### Phase 8 — Testing, Hardening, Deployment (Day 2, 5-10 PM)
- [ ] Unit tests: URL validation, parsing, schemas, normalization, confidence rules
- [ ] Integration tests: Postgres, Supabase auth, Ollama
- [ ] Security tests: SSRF (private IPs, metadata endpoint, redirect to internal, DNS rebinding), ownership, malformed uploads, prompt injection in page content
- [ ] E2E: import -> research -> report -> export
- [ ] Concurrency and job recovery (kill worker mid-job, verify lease expiry and resume)
- [ ] Run evaluation on 50 companies and record baseline metrics
- [ ] Secrets review, structured logging with request/job IDs
- [ ] Deploy frontend, backend, worker, database; HTTPS and CORS
- [ ] Smoke tests and known-limitations list

Exit: a real user can securely complete the core workflow on the deployed app; failures are visible and recoverable.

## 5. Schedule

| Day | Time | Work |
|-----|------|------|
| 1 | 9-10 AM | Phase 1 foundation |
| 1 | 10 AM-12 PM | Phase 2 lead management |
| 1 | 12-5 PM | Phase 3 website research + normalization |
| 1 | 5-9 PM | Phase 4 social discovery and first integration |
| 1 | 9-10 PM | Collection integration test |
| 2 | 9-11 AM | Phase 5 intelligence |
| 2 | 11 AM-1 PM | Phase 6 insights |
| 2 | 1-5 PM | Phase 7 workspace + integration |
| 2 | 5-10 PM | Phase 8 testing and deployment |

If a schedule slips, cut in this order: extra social platforms, CSV export polish, PDF styling, then research-page extras. Never cut SSRF protection, ownership enforcement or evidence validation.

## 6. Definition of done (per task)
- Code merged with tests for new logic.
- Types/schemas validated; no unhandled exceptions on bad input.
- Logs include request ID / job ID.
- No secrets in code or frontend bundle.
- Matches `API_SPEC.md` and `DATABASE_SCHEMA.md`, or the specs are updated in the same change.

## 7. Risks to watch
| Risk | Response |
|------|----------|
| Social API access/permissions | Keep adapter interface; ship what is permitted |
| LLM output quality on local hardware | Benchmark early; tighten context; keep `unknown` default |
| Worker crashes mid-job | Lease expiry and recovery tested in Phase 8 |
| JS-heavy sites | Record as partial; Playwright fallback only for selected sites |
| Scope creep | Section 17 exclusions in the blueprint are binding |

## 8. Post-MVP hardening list
Redis-backed durable queue, per-user quotas, human review workflow for findings, more social platforms, observability dashboards, backup/restore drills, report templates.

---

## Build status (v1.0)

All eight phases are implemented in this repository. Verified locally: 115 automated tests (unit, integration, end-to-end with a fake website, fake YouTube API and fake LLM) pass on SQLite and on PostgreSQL 16; the Alembic migration applies and rolls back on both, including RLS policies and evidence check constraints; the frontend type-checks and builds.

Not verified in the build environment (requires your credentials/hardware): a live Supabase project, a live Ollama model, the real YouTube Data API, and real third-party websites. Run `backend/scripts/benchmark_models.py` to choose the Ollama model, then run your 50-company evaluation set.
