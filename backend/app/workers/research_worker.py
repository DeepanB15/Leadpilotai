"""Separate worker process: claims jobs from PostgreSQL (SKIP LOCKED + leases) and runs them.

Run with:  python -m app.workers.research_worker
"""

import asyncio
import logging
import os
import signal
import socket
import uuid

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import SessionLocal
from app.research.orchestrator import ResearchDeps, build_default_deps, run_research_job
from app.services import job_service

log = logging.getLogger("worker")


class Worker:
    def __init__(self, deps: ResearchDeps, worker_id: str | None = None):
        self.deps = deps
        self.settings = deps.settings
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> bool:
        """Claim and run one job. Returns True if a job was processed."""
        with SessionLocal() as db:
            job = job_service.claim_next_job(db, self.worker_id, self.settings)
            job_id = job.id if job else None
        if job_id is None:
            return False
        log.info("claimed job", extra={"extra_fields": {"job_id": str(job_id), "worker": self.worker_id}})
        status = await run_research_job(job_id, SessionLocal, self.deps)
        log.info("job finished", extra={"extra_fields": {"job_id": str(job_id), "status": status}})
        return True

    async def _slot(self, n: int) -> None:
        while not self._stop.is_set():
            try:
                did = await self.run_once()
            except Exception:
                log.exception("worker slot %s crashed; continuing", n)
                did = False
            if not did:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.settings.worker_poll_seconds)
                except TimeoutError:
                    pass

    async def run(self) -> None:
        log.info("worker started", extra={"extra_fields": {"worker": self.worker_id, "slots": self.settings.worker_concurrency}})
        await asyncio.gather(*(self._slot(i) for i in range(max(1, self.settings.worker_concurrency))))
        log.info("worker stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker = Worker(build_default_deps(settings))

    async def _main():
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, worker.stop)
        await worker.run()

    asyncio.run(_main())


if __name__ == "__main__":
    main()
