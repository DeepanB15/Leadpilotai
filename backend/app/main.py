import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, request_id_var
from app.db import engine

settings = get_settings()
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(settings.log_level)
    log.info("api started", extra={"extra_fields": {"env": settings.app_env}})
    yield


app = FastAPI(title="LeadPilotAI API", version=settings.pipeline_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    token = request_id_var.set(rid[:64])
    try:
        response: Response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid[:64]
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


install_error_handlers(app)


def _health(response: Response) -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        response.status_code = 503
        return {"status": "degraded", "database": "error"}


@app.get("/health", include_in_schema=False)
def health_root(response: Response):
    return _health(response)


@app.get("/api/v1/health", tags=["health"])
def health(response: Response):
    return _health(response)


app.include_router(api_router, prefix="/api/v1")
