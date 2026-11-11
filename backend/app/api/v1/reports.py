import re
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthUser, get_current_user, get_db
from app.core.errors import NotFound
from app.models import Company, ResearchReport
from app.services import export_service

router = APIRouter(prefix="/reports", tags=["reports"])


def _load(db: Session, user: AuthUser, report_id: uuid.UUID) -> tuple[ResearchReport, Company]:
    row = db.scalar(select(ResearchReport).where(ResearchReport.id == report_id, ResearchReport.user_id == user.id))
    company = db.get(Company, row.company_id) if row else None
    if not row or not company or company.user_id != user.id:
        raise NotFound("Report not found")
    return row, company


@router.get("/{report_id}")
def get_report(report_id: uuid.UUID, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row, _ = _load(db, user, report_id)
    return {
        "id": str(row.id),
        "company_id": str(row.company_id),
        "job_id": str(row.job_id) if row.job_id else None,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        **row.report_data,
    }


@router.get("/{report_id}/export")
def export_report(
    report_id: uuid.UUID,
    format: str = Query("pdf", pattern="^(pdf|csv)$"),
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row, company = _load(db, user, report_id)
    slug = re.sub(r"[^a-z0-9]+", "-", company.name.lower()).strip("-") or "company"
    name = f"{slug}-report-v{row.version}.{format}"
    if format == "csv":
        body, media = export_service.report_to_csv(company, row.report_data, str(row.id)), "text/csv"
    else:
        body, media = export_service.report_to_pdf(company, row.report_data), "application/pdf"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
