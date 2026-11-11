# LeadPilotAI v1.0 — Product Requirements Document

Status: Baseline · Owner: Product/Engineering · Last updated: 2026-11-08

## 1. Product summary

LeadPilotAI is an AI-powered, multi-source B2B company research platform. It turns lists of companies into structured, evidence-backed **Company Intelligence Reports** using website research, social profile discovery, limited public content analysis and LLM-based business understanding.

- **Primary customer:** B2B SaaS sales, business development and growth teams.
- **Differentiator:** Deep, multi-source company research with traceable evidence.
- **Flagship output:** Unified Company Intelligence Report.
- **Philosophy:** Research first. Evidence first. Accuracy first. No unnecessary complexity.

## 2. Goals and non-goals

### Goals
1. Let a user add or import companies and start research in minutes.
2. Collect public information from company websites and permitted social sources.
3. Produce a structured company profile where every material fact links to evidence.
4. Separate observed facts, inferences and unknowns in every report.
5. Show honest research coverage (completed / partial / inaccessible / not discovered / unsupported / failed).
6. Provide grounded sales preparation (talking points, questions, value proposition, next action).

### Non-goals (v1)
Full CRM pipeline, lead scoring, automated outreach, social engagement analytics, audience demographics, competitor monitoring, Google Maps discovery, Chrome extension, multi-agent architecture, LangGraph, RAG/vector DB, dynamic model routing, Kafka/Kubernetes, distributed infrastructure.

## 3. Users and primary workflow

Persona: SDR / BDR / account executive / growth marketer preparing outreach to a list of target accounts.

```
Add or import companies -> Start research (single or batch) -> Monitor job status
-> Open company report -> Review insights + evidence -> Prepare outreach -> Export PDF/CSV
```

## 4. Modules and requirements

### M1 — Lead Management & Input (supporting)
| ID | Requirement | Priority |
|----|-------------|----------|
| M1-1 | Manual company creation (name, website, optional social URLs) | Must |
| M1-2 | CSV import with preview and confirmation | Must |
| M1-3 | Excel (.xlsx) import with preview and confirmation | Must |
| M1-4 | Validate names and URLs; reject or flag invalid rows | Must |
| M1-5 | Normalize URLs and detect duplicates by normalized domain, per user | Must |
| M1-6 | Start research for one company or a selected batch | Must |
| M1-7 | Status tracking: pending, processing, completed, partial, failed | Must |
| M1-8 | Delete company with confirmation safeguard | Basic |

Import columns: `company_name`, `website` (required); `linkedin_url`, `instagram_url`, `youtube_url`, `facebook_url`, `x_url`, `industry` (optional).

### M2 — Multi-Source Research Engine (core)
**Website research (2A)**
- Validate/normalize URL; fetch homepage with HTTPX; discover internal pages.
- Priority pages: homepage, about, products, services, solutions, pricing (if accessible), contact, blog/news.
- Configurable crawl limit (default: 10 pages per company); never crawl whole sites.
- Extract main content (Trafilatura), clean, normalize, de-duplicate by content hash.
- Preserve source URL, HTTP status, extraction method, content hash and collection timestamp.
- Record inaccessible pages and errors. Playwright only as a fallback for selected JS-heavy sites.

**Social research (2B)**
- Discovery: links extracted from website, user-supplied URLs, optional approved search provider.
- Verify profile identity before association; never assume a match by name alone. States: `verified`, `unverified`, `rejected`.
- Per-platform adapter (LinkedIn, Instagram, YouTube, Facebook, X) implementing only supported methods.
- Collect profile metadata and a limited sample of recent public content where access is permitted.
- Unsupported or blocked platforms return explicit `unsupported` / `access_unavailable`; never fabricate content.
- No engagement statistics required in v1.
- Failure of one source never stops others.

### M3 — Company Intelligence Engine (core)
- LLM (Ollama) analyzes only normalized source documents; it does not crawl or invent.
- Extracts: identity, industry, description, business model, products, services, target customers, positioning, digital presence, content positioning.
- Output is versioned Pydantic-validated JSON with field-level evidence references.
- Unsupported fields return `unknown`. Invalid output is retried or recorded as an error and never corrupts stored records.

### M4 — Research Intelligence & Insights (flagship)
- Findings: notable characteristics, evidence-backed strengths, digital presence observations, website/enquiry-pathway observations, social themes, public announcements, potential opportunities, talking points.
- Every finding is classified `observed_fact`, `inference` or `unknown`.
- Confidence labels High / Medium / Low computed deterministically from evidence quality, source reliability, number of independent sources, consistency, recency and extraction completeness. The LLM does not assign confidence freely.
- Research completeness states per source: completed, partial, inaccessible, not discovered, unsupported, failed. An inaccessible source is never reported as "no presence".
- Sales preparation: talking points, prospect questions, potential value proposition, suggested next action, all grounded in the report.

### M5 — Research Workspace (supporting)
- Routes: `/login`, `/dashboard`, `/companies`, `/companies/new`, `/companies/[id]`, `/research`, `/settings`.
- Dashboard: total, completed, processing, failed/partial counts; company list; search and filters.
- Company detail sections: Overview, Website, Social, Insights, Evidence & Sources, Sales Prep.
- Research page: job list, stage, per-source status, errors, retry, timestamps.
- Export: PDF (overview, findings, sources, confidence, timestamps) and CSV (companies and selected findings).
- UI direction: white background, thin bottom borders, compact controls, small type, minimal icons, neutral gray. No decorative charts, no CRM features. No placeholder data presented as research.

## 5. Non-functional requirements

**Security**
- Supabase Auth; backend verifies bearer token; user ID derived from token only.
- Ownership enforced in every query; RLS enabled; service-role key backend-only.
- SSRF protection: http/https only, restricted ports, block loopback/private/link-local/metadata addresses, validate DNS results and every redirect, DNS-rebinding protection, timeouts, response size limits, content-type checks, per-domain rate limits.
- LLM safety: collected content is untrusted; embedded instructions ignored; output and evidence references validated; input/output size limits.

**Reliability**
- Research runs in a separate worker, not in request handlers or FastAPI BackgroundTasks.
- Atomic job claiming with leases and recovery of abandoned jobs.
- Retries only for transient errors, with exponential backoff; bounded concurrency.
- Structured logging with request and job IDs; model and prompt version tracking.

**Performance (initial targets, to be measured)**
- Research request returns a job ID immediately (< 1 s).
- Typical single-company research completes within a few minutes on target hardware (baseline to be measured).

## 6. Job state machine

`queued -> discovering -> researching -> analyzing -> generating_report -> completed | partial | failed`; `cancelled` from any non-terminal state by user.

## 7. Acceptance criteria

| Category | Criteria |
|----------|----------|
| Authentication | Users securely access only their own workspace |
| Company input | Manual entry and CSV/Excel import work |
| Website research | Accessible pages extracted and stored with source URLs |
| Social discovery | Official profiles discovered or supplied; verification state stored |
| Social content | Limited permitted content collected; unsupported platforms handled honestly |
| Company intelligence | Valid structured profiles generated; unsupported fields `unknown` |
| Findings | Evidence-backed; observed/inferred/unknown separated |
| Confidence | Deterministic and explainable |
| Source tracking | Every material finding traceable or labelled inference |
| Job management | One failure never stops a batch |
| Reports | Viewable and exportable (PDF, CSV) |
| Security | Auth, ownership and SSRF protections tested |

### Evaluation (50 real companies)
| Metric | Target |
|--------|--------|
| Companies processed | 50 |
| Required fields populated or explicitly unknown | >= 90% |
| Material findings traceable or labelled inference | 100% |
| Batch-wide failure from one company | None |
| Report usability | Human-validated |

Targets are evaluation goals, not performance claims; the baseline must be measured.

## 8. Risks and mitigations
| Risk | Mitigation |
|------|-----------|
| Social platform access restrictions | Adapter interface; ship at least one permitted integration; honest `access_unavailable` states; do not bypass restrictions |
| LLM hallucination | Evidence-only prompts, Pydantic validation, evidence-reference checks, `unknown` default |
| SSRF via user URLs | Dedicated validated fetcher used by all outbound requests |
| Local hardware limits for Ollama | Benchmark candidate models; start with one model; context selection |
| 48-hour schedule | Prioritize end-to-end path over breadth; defer extra platforms |

## 9. Open questions
1. Which Ollama model meets quality/latency on target hardware (benchmark needed)?
2. Which social platform is the first permitted integration (YouTube public data is the likely candidate)?
3. Which approved search provider, if any, for social discovery?
4. Deployment targets for frontend, backend, worker and Ollama.
