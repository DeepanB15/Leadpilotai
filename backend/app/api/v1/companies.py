import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthUser, get_current_user, get_db
from app.core.errors import NotFound
from app.models import Company, CompanyProfile, ResearchFinding, ResearchReport, ResearchSource, SourceDocument
from app.schemas.company import CompanyCreate, CompanyList, CompanyOut, CompanyUpdate, DashboardStats
from app.schemas.research import (
    DocumentOut,
    FindingList,
    FindingOut,
    ProfileOut,
    ReportSummary,
    ReportSummaryList,
    SourceList,
    SourceOut,
)
from app.services import company_service, export_service, report_service

router = APIRouter(tags=["companies"])


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return company_service.dashboard_stats(db, user.id)


@router.get("/companies", response_model=CompanyList)
def list_companies(
    q: str | None = Query(None, max_length=100),
    status: str | None = Query(None, max_length=32),
    sort: str = Query("-created_at", max_length=32),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = company_service.list_companies(db, user.id, q=q, status=status, limit=limit, offset=offset, sort=sort)
    return CompanyList(items=items, total=total)


@router.get("/companies/export/csv")
def export_companies_csv(user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Company).where(Company.user_id == user.id).order_by(Company.created_at.desc())))
    return Response(
        export_service.companies_to_csv(rows),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="companies.csv"'},
    )


@router.post("/companies", response_model=CompanyOut, status_code=201)
def create_company(data: CompanyCreate, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return CompanyOut.model_validate(company_service.create_company(db, user.id, data))


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: uuid.UUID, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    company = company_service.get_company(db, user.id, company_id)
    out = CompanyOut.model_validate(company)
    plats = company_service._platforms(db, user.id, [company.id]).get(company.id, set())
    out.platforms = sorted(set(company.social_urls()) | plats)
    return out


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: uuid.UUID,
    data: CompanyUpdate,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CompanyOut.model_validate(company_service.update_company(db, user.id, company_id, data))


@router.delete("/companies/{company_id}", status_code=204)
def delete_company(company_id: uuid.UUID, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    company_service.delete_company(db, user.id, company_id)
    return Response(status_code=204)


# --------------------------------------------------------------- research data


@router.get("/companies/{company_id}/sources", response_model=SourceList)
def list_sources(
    company_id: uuid.UUID,
    include: str | None = Query(None, pattern="^documents$"),
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = company_service.get_company(db, user.id, company_id)
    sources = list(db.scalars(select(ResearchSource).where(ResearchSource.company_id == company.id)))
    counts = dict(
        db.execute(
            select(SourceDocument.source_id, func.count())
            .where(SourceDocument.company_id == company.id)
            .group_by(SourceDocument.source_id)
        ).all()
    )
    docs_by_source: dict[uuid.UUID, list[SourceDocument]] = {}
    if include == "documents":
        for d in db.scalars(
            select(SourceDocument).where(SourceDocument.company_id == company.id).order_by(SourceDocument.collected_at.desc())
        ):
            docs_by_source.setdefault(d.source_id, []).append(d)
    items = []
    for s in sorted(sources, key=lambda s: (s.platform != "website", s.platform)):
        items.append(
            SourceOut(
                id=s.id,
                platform=s.platform,
                source_type=s.source_type,
                source_url=s.source_url,
                discovery_method=s.discovery_method,
                verification_status=s.verification_status,
                access_status=s.access_status,
                status_detail=s.status_detail,
                profile_metadata=s.profile_metadata,
                last_checked_at=s.last_checked_at,
                document_count=counts.get(s.id, 0),
                documents=[DocumentOut.model_validate(d) for d in docs_by_source.get(s.id, [])]
                if include == "documents"
                else None,
            )
        )
    return SourceList(items=items, coverage=report_service.build_coverage(sources, counts))


@router.get("/companies/{company_id}/profile", response_model=ProfileOut)
def get_profile(
    company_id: uuid.UUID,
    version: int | None = Query(None, ge=1),
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = company_service.get_company(db, user.id, company_id)
    stmt = select(CompanyProfile).where(CompanyProfile.company_id == company.id)
    stmt = stmt.where(CompanyProfile.version == version) if version else stmt.order_by(CompanyProfile.version.desc())
    row = db.scalars(stmt.limit(1)).first()
    if not row:
        raise NotFound("No company profile has been generated yet")
    return ProfileOut(
        version=row.version,
        model_id=row.model_id,
        schema_version=row.schema_version,
        prompt_version=row.prompt_version,
        generated_at=row.generated_at,
        profile_data=row.profile_data,
        fields=row.evidence_refs,
    )


@router.get("/companies/{company_id}/findings", response_model=FindingList)
def list_findings(
    company_id: uuid.UUID,
    classification: str | None = Query(None, pattern="^(observed_fact|inference|unknown)$"),
    confidence: str | None = Query(None, pattern="^(high|medium|low)$"),
    finding_type: str | None = Query(None, max_length=40),
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = company_service.get_company(db, user.id, company_id)
    # Findings from the most recent job only; history stays in older reports.
    latest_job = db.scalar(
        select(ResearchFinding.job_id)
        .where(ResearchFinding.company_id == company.id)
        .order_by(ResearchFinding.created_at.desc())
        .limit(1)
    )
    stmt = select(ResearchFinding).where(ResearchFinding.company_id == company.id)
    if latest_job:
        stmt = stmt.where(ResearchFinding.job_id == latest_job)
    if classification:
        stmt = stmt.where(ResearchFinding.classification == classification)
    if confidence:
        stmt = stmt.where(ResearchFinding.confidence == confidence)
    if finding_type:
        stmt = stmt.where(ResearchFinding.finding_type == finding_type)
    rows = list(db.scalars(stmt.order_by(ResearchFinding.created_at, ResearchFinding.id)))
    return FindingList(items=[FindingOut.model_validate(r) for r in rows], total=len(rows))


@router.get("/companies/{company_id}/reports", response_model=ReportSummaryList)
def list_reports(company_id: uuid.UUID, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    company = company_service.get_company(db, user.id, company_id)
    rows = list(
        db.scalars(
            select(ResearchReport).where(ResearchReport.company_id == company.id).order_by(ResearchReport.version.desc())
        )
    )
    return ReportSummaryList(items=[ReportSummary.model_validate(r) for r in rows], total=len(rows))
