"""Benchmark candidate Ollama models on real company websites.

Usage (from backend/):
    python -m scripts.benchmark_models --models llama3.1:8b qwen2.5:7b --sites https://example.com https://another.com

For each site the pages are crawled once (SSRF-safe crawler), then every model runs the profile
extraction. Reported per run: success, attempts needed, seconds, fields known vs unknown, and
claims rejected by the evidence validator. Use it to pick ONE model before the 50-company evaluation.
"""

import argparse
import asyncio
import time

from app.core.config import get_settings
from app.intelligence.company_analyzer import AnalysisError, analyze_company
from app.intelligence.docs import DocRef, build_index
from app.intelligence.model_client import OllamaClient
from app.research.safe_fetch import DomainRateLimiter, SafeFetcher
from app.research.website.crawler import RobotsChecker, crawl_website
from app.utils.time import utcnow
from app.utils.urls import normalize_website
import uuid


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--sites", nargs="+", required=True)
    args = ap.parse_args()
    s = get_settings()

    fetcher = SafeFetcher(timeout=s.fetch_timeout_seconds, rate_limiter=DomainRateLimiter(1.0), user_agent=s.user_agent)
    robots = RobotsChecker(fetcher, s.user_agent, True)
    corpora = {}
    for site in args.sites:
        n = normalize_website(site)
        crawl = await crawl_website(fetcher, robots, n.url, max_pages=s.crawl_max_pages)
        src = uuid.uuid4()
        refs = [
            DocRef(uuid.uuid4(), src, "website", d.url, d.document_type, d.title, d.content, utcnow(), metadata=d.metadata)
            for d in crawl.docs
        ]
        corpora[n.domain] = refs
        print(f"crawled {n.domain}: {len(refs)} documents ({crawl.status.value})")

    print(f"\n{'model':24} {'site':24} {'ok':3} {'tries':5} {'sec':6} {'known':5} {'unknown':7} {'rejected':8}")
    for model in args.models:
        llm = OllamaClient(s.ollama_base_url, model, timeout=s.ollama_timeout_seconds, num_ctx=s.ollama_num_ctx)
        for domain, refs in corpora.items():
            if not refs:
                continue
            t0 = time.time()
            try:
                res = await analyze_company(llm, domain, domain, build_index(refs), s)
                known = sum(1 for f in res.fields if f["classification"] != "unknown")
                unk = sum(1 for f in res.fields if f["classification"] == "unknown")
                print(f"{model:24} {domain:24} {'yes':3} {res.attempts:<5} {time.time()-t0:<6.1f} {known:<5} {unk:<7} {res.rejected_claims:<8}")
            except AnalysisError as exc:
                print(f"{model:24} {domain:24} {'no':3} {'-':5} {time.time()-t0:<6.1f} {'-':5} {'-':7} {'-':8}  {str(exc)[:60]}")
        await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
