from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import AuthUser, get_current_user, get_db
from app.core.config import get_settings
from app.core.errors import FileTooLarge, ValidationFailed
from app.services import import_service
from app.services.rate_limit import check_rate_limit

router = APIRouter(prefix="/imports", tags=["imports"])


async def _read_limited(request: Request, file: UploadFile) -> bytes:
    limit = get_settings().import_max_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + 4096:
        raise FileTooLarge(f"File exceeds {limit // (1024 * 1024)} MB limit")
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise FileTooLarge(f"File exceeds {limit // (1024 * 1024)} MB limit")
    return data


async def _handle(kind: str, request: Request, file: UploadFile, mode: str, user: AuthUser, db: Session):
    check_rate_limit(str(user.id), "import", get_settings().rate_limit_import_per_min)
    name = (file.filename or "").lower()
    if kind == "csv" and not name.endswith((".csv", ".txt")):
        raise ValidationFailed("Please upload a .csv file")
    if kind == "xlsx" and not name.endswith(".xlsx"):
        raise ValidationFailed("Please upload an .xlsx file")
    content = await _read_limited(request, file)
    rows = import_service.parse_table(kind, content)
    return import_service.process_import(db, user.id, rows, commit=(mode == "commit"))


@router.post("/csv")
async def import_csv(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Query("preview", pattern="^(preview|commit)$"),
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await _handle("csv", request, file, mode, user, db)


@router.post("/excel")
async def import_excel(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Query("preview", pattern="^(preview|commit)$"),
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await _handle("xlsx", request, file, mode, user, db)
