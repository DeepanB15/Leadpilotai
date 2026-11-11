"""Research orchestration: one job = one company, sources processed independently.

Stages: discovering -> researching (website, social) -> analyzing -> generating_report -> completed|partial|failed
A failure in any single source or AI step never aborts the others; the report records what happened.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import job_id_var
from app.enums import AccessStatus, JobStatus, Platform, SourceType, VerificationStatus
from app.intelligence.company_analyzer import AnalysisError, ProfileResult, analyze_company
from app.intelligence.docs import DocRef, build_index
from app.intelligence.insight_generator import InsightsResult, generate_insights
from app.intelligence.model_client import LLMClient, OllamaClient
from app.models import Company, CompanyProfile, ResearchFinding, ResearchJob, ResearchSource, SourceDocument
from app.research.discovery.social_links import discover_social_sources
from app.research.safe_fetch import DomainRateLimiter, SafeFetcher
from app.research.social.base import AdapterOutcome, SocialContext, SocialResearchAdapter
from app.research.social.registry import build_adapters
from app.research.website.crawler import CrawlResult, RobotsChecker, crawl_website
from app.services import job_service, report_service, source_store
from app.utils.time import utcnow

log = logging.getLogger(__name__)

SOCIAL_TIMEOUT_SECONDS = 90


@dataclass
class ResearchDeps:
    settings: Settings
    fetcher: SafeFetcher
    robots: RobotsChecker
    llm: LLMClient
    adapters: dict[str, SocialResearchAdapter]


def build_default_deps(settings: Settings) -> ResearchDeps:
    fetcher = SafeFetcher(
        timeout=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
        max_redirects=settings.fetch_max_redirects,
        user_agent=settings.user_agent,
        rate_limiter=DomainRateLimiter(settings.domain_min_interval_seconds),
    )
    return ResearchDeps(
        settings=settings,
        fetcher=fetcher,
        robots=RobotsChecker(fetcher, settings.user_agent, settings.respect_robots_txt),
        llm=OllamaClient(
            settings.ollama_base_url,
            settings.ollama_model,
            timeout=settings.ollama_timeout_seconds,
            num_ctx=settings.ollama_num_ctx,
        ),
        adapters=build_adapters(settings),
    )


async def run_research_job(job_id: uuid.UUID, session_factory: Callable[[], Session], deps: ResearchDeps) -> str:
    """Execute a claimed job to completion. Returns the final job status."""
    job_id_var.set(str(job_id))
    with session_factory() as db:
        job = db.get(ResearchJob, job_id)
        if job is None:
            return "missing"
        company = db.get(Company, job.company_id)
        if company is None:
            job_service.finish_job(db, job, JobStatus.failed, error_info={"error": "Company no longer exists"})
            return JobStatus.failed.value
        try:
            status = await _run(db, job, company, deps)
        except job_service.JobCancelled:
            log.info("job cancelled")
            return JobStatus.cancelled.value
        except Exception as exc:
            log.exception("research job crashed")
            db.rollback()
            job = db.get(ResearchJob, job_id)
            job_service.finish_job(
                db,
                job,
                JobStatus.failed,
                error_info={"stage": job.progress_stage, "error": f"{exc.__class__.__name__}: {exc}"[:500]},
            )
            return JobStatus.failed.value
        return status


def _doc_refs(pairs: list[tuple[ResearchSource, SourceDocument]]) -> list[DocRef]:
    refs = []
    for src, d in pairs:
        if src.verification_status == VerificationStatus.rejected.value:
            continue
        refs.append(
            DocRef(
                id=d.id,
                source_id=src.id,
                platform=src.platform,
                url=d.url,
                document_type=d.document_type,
                title=d.title,
                content=d.content,
                collected_at=d.collected_at,
                published_at=d.published_at,
                verification_status=src.verification_status,
                source_access_status=src.access_status,
                metadata=d.meta or {},
            )
        )
    return refs


async def _research_social_one(adapter: SocialResearchAdapter | None, platform: str, url: str, ctx: SocialContext):
    if adapter is None:
        return AdapterOutcome(
            platform=platform, url=url, access_status=AccessStatus.unsupported, detail="No adapter registered"
        )
    try:
        return await asyncio.wait_for(adapter.research(url, ctx), timeout=SOCIAL_TIMEOUT_SECONDS)
    except TimeoutError:
        return AdapterOutcome(platform=platform, url=url, access_status=AccessStatus.failed, detail="Timed out")
    except Exception as exc:  # last-resort isolation
        log.exception("social adapter crashed: %s", platform)
        return AdapterOutcome(
            platform=platform, url=url, access_status=AccessStatus.failed, detail=f"{exc.__class__.__name__}"
        )


async def _run(db: Session, job: ResearchJob, company: Company, deps: ResearchDeps) -> str:
    s = deps.settings
    pairs: list[tuple[ResearchSource, SourceDocument]] = []

    # ---------------------------------------------------------------- website
    job_service.set_stage(db, job, JobStatus.discovering, "source_discovery", s)
    job_service.set_stage(db, job, JobStatus.researching, "website_research", s)
    web_src = source_store.upsert_source(
        db,
        company=company,
        job=job,
        source_type=SourceType.website.value,
        platform=Platform.website.value,
        url=company.website_url,
        discovery_method="user_supplied",
        verification=VerificationStatus.verified,
        access=AccessStatus.failed,
        detail="Research in progress",
    )
    db.commit()
    try:
        crawl = await crawl_website(deps.fetcher, deps.robots, company.website_url, max_pages=s.crawl_max_pages)
    except Exception as exc:
        log.exception("website crawl crashed")
        crawl = CrawlResult(status=AccessStatus.failed, detail=f"Unexpected error: {exc.__class__.__name__}")
    saved = source_store.save_documents(db, web_src, company, crawl.docs)
    source_store.update_source(
        db,
        web_src,
        access=crawl.status,
        detail=crawl.detail,
        metadata={
            "pages_collected": len(crawl.docs),
            "page_errors": [{"url": e.url, "error": e.error} for e in crawl.errors][:20],
            "site_description": crawl.site_description,
        },
    )
    pairs.extend((web_src, d) for d in saved)
    db.commit()

    # ----------------------------------------------------------------- social
    job_service.set_stage(db, job, JobStatus.researching, "social_research", s)
    discovered, website_keys = discover_social_sources(company.social_urls(), crawl.social_urls)
    tasks = []
    for d in discovered:
        ctx = SocialContext(
            company_name=company.name,
            company_domain=company.normalized_domain,
            website_social_keys=website_keys,
            user_supplied=d.user_supplied,
            limit=s.social_content_limit,
        )
        tasks.append(_research_social_one(deps.adapters.get(d.platform), d.platform, d.url, ctx))
    outcomes = await asyncio.gather(*tasks)
    for d, outcome in zip(discovered, outcomes, strict=True):
        src = source_store.upsert_source(
            db,
            company=company,
            job=job,
            source_type=SourceType.social.value,
            platform=d.platform,
            url=d.url,
            discovery_method=d.method,
            verification=outcome.verification_status,
            access=outcome.access_status,
            detail=outcome.detail
            or (outcome.verification_reason if outcome.verification_status != VerificationStatus.verified else None),
            profile_metadata=(
                {
                    "display_name": outcome.profile.display_name,
                    "handle": outcome.profile.handle,
                    "verification_reason": outcome.verification_reason,
                    **outcome.profile.metadata,
                }
                if outcome.profile
                else {"verification_reason": outcome.verification_reason}
            ),
        )
        docs = source_store.save_documents(db, src, company, outcome.to_documents())
        pairs.extend((src, x) for x in docs)
    db.commit()

    # --------------------------------------------------------------- analysis
    job_service.set_stage(db, job, JobStatus.analyzing, "company_analysis", s)
    refs = _doc_refs(pairs)
    sources = list(db.scalars(select(ResearchSource).where(ResearchSource.company_id == company.id)))
    counts = {src.id: sum(1 for r in refs if r.source_id == src.id) for src in sources}
    coverage = report_service.build_coverage(sources, counts)

    profile_row: CompanyProfile | None = None
    profile_result: ProfileResult | None = None
    insights: InsightsResult | None = None
    analysis_error: str | None = None
    now = utcnow()

    if refs:
        index = build_index(refs)
        try:
            profile_result = await analyze_company(deps.llm, company.name, company.normalized_domain, index, s)
        except AnalysisError as exc:
            analysis_error = str(exc)[:400]
            log.warning("company analysis failed: %s", analysis_error)

        if profile_result:
            version = (
                db.scalar(select(func.max(CompanyProfile.version)).where(CompanyProfile.company_id == company.id)) or 0
            ) + 1
            profile_row = CompanyProfile(
                company_id=company.id,
                job_id=job.id,
                user_id=company.user_id,
                version=version,
                profile_data=profile_result.profile_data,
                evidence_refs=profile_result.fields,
                model_id=profile_result.model_id,
                schema_version=s.schema_version,
                prompt_version=s.prompt_version,
            )
            db.add(profile_row)
            ind = profile_result.profile_data["company_overview"]["industry"]
            if ind != "unknown" and not company.industry:
                company.industry = ind[:200]
            db.commit()

            job_service.set_stage(db, job, JobStatus.analyzing, "insights", s)
            try:
                insights = await generate_insights(
                    deps.llm,
                    company.name,
                    company.normalized_domain,
                    profile_result.profile_data,
                    index,
                    report_service.coverage_note(coverage),
                    s,
                    now,
                )
            except AnalysisError as exc:
                analysis_error = str(exc)[:400]
                log.warning("insight generation failed: %s", analysis_error)

    # ----------------------------------------------------------------- report
    job_service.set_stage(db, job, JobStatus.generating_report, "report", s)
    finding_dicts: list[dict] = []
    if insights:
        for f in insights.findings:
            row = ResearchFinding(
                id=f.id,
                company_id=company.id,
                job_id=job.id,
                user_id=company.user_id,
                finding_type=f.finding_type,
                classification=f.classification,
                title=f.title,
                description=f.description,
                evidence=f.evidence,
                confidence=f.confidence,
                confidence_factors=f.confidence_factors,
            )
            db.add(row)
            finding_dicts.append(report_service.finding_to_dict(row))
    db.flush()

    limitations = report_service.build_limitations(
        coverage, analysis_error=analysis_error, has_profile=profile_result is not None
    )
    if not refs:
        limitations.append("No usable documents were collected, so no analysis could be performed.")

    # Final status
    discovered_cov = [c for c in coverage if c["status"] != AccessStatus.not_discovered.value]
    website_cov = next(c for c in coverage if c["platform"] == "website")
    issues = any(c["status"] != AccessStatus.completed.value for c in discovered_cov)
    if not refs:
        final = JobStatus.failed
        error_info = {"stage": "research", "error": website_cov.get("detail") or "No usable documents collected"}
    elif analysis_error or profile_result is None:
        final, error_info = JobStatus.partial, {"stage": "analysis", "error": analysis_error}
    elif issues or website_cov["status"] != AccessStatus.completed.value:
        final, error_info = JobStatus.partial, None
    else:
        final, error_info = JobStatus.completed, None

    report = report_service.assemble_report(
        company=company,
        job_status=final.value,
        profile_data=profile_result.profile_data if profile_result else None,
        profile_fields=profile_result.fields if profile_result else None,
        profile_version=profile_row.version if profile_row else None,
        findings=finding_dicts,
        sales_preparation=insights.sales_preparation if insights else None,
        coverage=coverage,
        docs=refs,
        limitations=limitations,
        analysis_error=analysis_error,
        model_id=profile_result.model_id if profile_result else None,
        settings=s,
    )
    report_service.save_report(db, company, job.id, report)
    db.commit()
    job_service.finish_job(
        db, job, final, error_info=error_info, model_id=profile_result.model_id if profile_result else None
    )
    return final.value
