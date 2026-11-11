from fastapi import APIRouter

from app.api.v1 import companies, imports, reports, research

api_router = APIRouter()
api_router.include_router(companies.router)
api_router.include_router(imports.router)
api_router.include_router(research.router)
api_router.include_router(reports.router)
