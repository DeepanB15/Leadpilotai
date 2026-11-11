# LeadPilotAI v1.0

AI-powered, multi-source B2B company research. Add or import companies, research their websites and permitted social profiles, and get an evidence-backed **Company Intelligence Report** (profile, findings with confidence, sales preparation, honest coverage/limitations) with PDF/CSV export.

**Stack:** Next.js 14 (TypeScript, Tailwind) · FastAPI · Supabase (Auth + PostgreSQL) · SQLAlchemy/Alembic · Ollama · DB-backed worker.

```
frontend/   Next.js app (login, dashboard, companies, company report, research jobs, settings)
backend/    FastAPI API + research worker (modular monolith)
  app/api         HTTP endpoints            app/research      safe fetch, website + social research, orchestrator
  app/services    business logic            app/intelligence  Ollama client, prompts, evidence validation, confidence
  app/models      SQLAlchemy models         app/workers       job worker (SKIP LOCKED + leases)
  migrations      Alembic                   tests             unit / integration / e2e
docs/       PRD, DATABASE_SCHEMA, API_SPEC, IMPLEMENTATION_PLAN
samples/    companies.csv import example
```

## Quick start

### 1. Supabase
1. Create a project. Copy the **Project URL**, **anon key**, and the **database connection string**.
2. Auth works with email/password out of the box (disable "Confirm email" for faster local testing, or confirm via email).
3. Token verification: the backend uses the project's JWKS (`SUPABASE_URL`) for asymmetric keys, or `SUPABASE_JWT_SECRET` for legacy HS256 projects.

### 2. Configure
```bash
cp .env.example .env      # fill in Supabase values, OLLAMA_MODEL, optional YOUTUBE_API_KEY
```

### 3a. Docker
```bash
docker compose up --build                       # backend (runs migrations), worker, frontend
docker compose --profile ollama up --build      # also run Ollama in a container
docker compose exec ollama ollama pull llama3.1:8b
```
Open http://localhost:3000.

### 3b. Without Docker
```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
set -a; source ../.env; set +a
alembic upgrade head
uvicorn app.main:app --reload                   # terminal 1
python -m app.workers.research_worker           # terminal 2 (research runs here, not in the API)

# frontend
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

### 4. Use it
Sign up → **Add company** (or **Import CSV / Excel**, see `samples/companies.csv`) → **Research** → open the company to read the report → export PDF/CSV.

## Choosing the Ollama model
Don't assume the largest model is best. From `backend/`:
```bash
python -m scripts.benchmark_models --models llama3.1:8b qwen2.5:7b --sites https://site1.com https://site2.com
```
It reports JSON validity, retries needed, latency, known vs unknown fields and claims rejected by the evidence validator. Pick one model, set `OLLAMA_MODEL`, then run your 50-company evaluation.

## How accuracy is enforced
- The LLM sees only collected documents (labelled D1, D2…), fenced as untrusted data; embedded instructions are ignored and fence-breaking text is sanitized.
- Every material claim must cite a document **and quote text that actually appears in it** (whitespace/case-insensitive match). Unsupported claims become `unknown` (profile) or are dropped (findings). Invalid JSON is retried with feedback, then recorded as an analysis error — it never writes a bad profile.
- Each finding is `observed_fact`, `inference` or `unknown`. Opportunities are always inferences. Sales talking points must reference real findings or they are discarded.
- Confidence is deterministic and explained per finding (points table in `docs/IMPLEMENTATION_PLAN.md`, code in `app/intelligence/confidence.py`); inference is capped at medium.
- Coverage is honest per source: `completed / partial / inaccessible / not_discovered / unsupported / failed`. An unreachable LinkedIn is reported as unreachable, never as "no presence".

## Security
- Supabase JWT verified on every protected endpoint; user id comes from the token only; every query is owner-scoped (other users' records return 404); RLS policies are created by the migration; the service-role key is never used by the frontend.
- **SSRF protection** for all user-influenced fetches (`app/research/safe_fetch.py`): http/https and ports 80/443 only, no credentials, hostnames resolved and *all* addresses must be public (blocks loopback, private, link-local/cloud metadata, CGNAT, reserved, multicast, IPv4-mapped/NAT64/6to4, numeric-encoded hosts), connection pinned to the validated IP (DNS-rebinding), every redirect re-validated, timeouts, decoded-size cap, content-type allowlist, per-domain rate limit, robots.txt honoured.
- Upload limits (size, rows), per-user rate limits, structured JSON logs with request/job ids.

## Tests
```bash
cd backend && python -m pytest -q                                   # SQLite
TEST_DATABASE_URL=postgresql://user@host/testdb python -m pytest -q # PostgreSQL
cd frontend && npx tsc --noEmit && npm run build
```
115 tests cover URL validation, SSRF (incl. redirects and rebinding), parsing/extraction, evidence validation, confidence rules, auth, ownership isolation, CRUD, CSV/Excel import, job claiming/lease recovery/cancel, and the full pipeline (success, partial, website down, SSRF target, LLM outage, batch isolation, re-run versioning, PDF/CSV export).

## Known limitations (read before relying on it)
- **Social coverage is deliberately narrow.** YouTube (official Data API, needs `YOUTUBE_API_KEY`) is the only content integration. LinkedIn, Instagram, Facebook and X have no permitted public API access without authorization/paid tiers, so their URLs are recorded and reported as `unsupported` — nothing is scraped or invented. Add an adapter in `app/research/social/` when you obtain access.
- **JavaScript-heavy sites** may yield thin content and are marked `partial`; there is no Playwright fallback in v1 (add one in `app/research/website/crawler.py` for selected sites).
- The worker is a PostgreSQL-backed queue (atomic claim, leases, recovery). Move to Redis/RQ-style workers if you outgrow it. Rate limits are in-memory (per API instance).
- LLM quality depends on the model you choose and your hardware; run the benchmark and your evaluation set. The 90%/100% targets in the PRD are goals to measure, not guarantees.
- Not exercised in the build environment: a live Supabase project, live Ollama, the real YouTube API and real third-party sites (everything external was simulated in tests).

## Deployment notes
Frontend → any Node host or Docker (`frontend/Dockerfile`, standalone output). Backend + worker → the same image (`backend/Dockerfile`; worker overrides the command). Put the API behind HTTPS, set `CORS_ORIGINS` to the frontend origin, run `alembic upgrade head` once per release, and keep Ollama reachable from the worker only. Health check: `GET /health`.
