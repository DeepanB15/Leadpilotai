"""CSV / Excel import with validation, URL normalization, duplicate detection and preview/commit."""

import csv
import io
import re
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import FileTooLarge, ValidationFailed
from app.models import Company
from app.schemas.company import CompanyCreate
from app.utils.urls import normalize_website

ALIASES = {
    "name": {"name", "company_name", "company", "companyname", "organization", "account"},
    "website_url": {"website", "website_url", "url", "domain", "site", "company_website", "websiteurl"},
    "linkedin_url": {"linkedin", "linkedin_url", "linkedin_company"},
    "instagram_url": {"instagram", "instagram_url"},
    "youtube_url": {"youtube", "youtube_url"},
    "facebook_url": {"facebook", "facebook_url"},
    "x_url": {"x", "x_url", "twitter", "twitter_url"},
    "industry": {"industry", "sector"},
}
REQUIRED = ("name", "website_url")


def _canon_header(h: Any) -> str | None:
    key = re.sub(r"[^a-z0-9]+", "_", str(h or "").strip().lower()).strip("_")
    for canon, names in ALIASES.items():
        if key in names:
            return canon
    return None


def _read_csv(content: bytes) -> list[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    try:
        return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text))]
    except csv.Error as exc:
        raise ValidationFailed(f"Could not parse CSV: {exc}") from exc


def _read_xlsx(content: bytes) -> list[list[str]]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = [["" if v is None else str(v).strip() for v in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    except Exception as exc:
        raise ValidationFailed("Could not read the Excel file; ensure it is a valid .xlsx workbook") from exc


def parse_table(kind: str, content: bytes) -> list[tuple[int, dict[str, str]]]:
    settings = get_settings()
    if len(content) > settings.import_max_bytes:
        raise FileTooLarge(f"File exceeds {settings.import_max_bytes // (1024 * 1024)} MB limit")
    if kind == "xlsx" and not content.startswith(b"PK"):
        raise ValidationFailed("File is not a valid .xlsx workbook")
    raw = _read_xlsx(content) if kind == "xlsx" else _read_csv(content)
    raw = [r for r in raw if any(c for c in r)] if raw else []
    if not raw:
        raise ValidationFailed("The file is empty")

    header = [_canon_header(h) for h in raw[0]]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        labels = {"name": "company_name", "website_url": "website"}
        raise ValidationFailed(
            "Missing required column(s): " + ", ".join(labels[m] for m in missing),
            details={"found_columns": [str(h) for h in raw[0]]},
        )
    data_rows = raw[1:]
    if len(data_rows) > settings.import_max_rows:
        raise ValidationFailed(f"Too many rows (max {settings.import_max_rows})")

    out: list[tuple[int, dict[str, str]]] = []
    # original spreadsheet row numbers (header is row 1); blank rows were dropped so recompute conservatively
    for i, row in enumerate(data_rows, start=2):
        rec: dict[str, str] = {}
        for col, val in zip(header, row, strict=False):
            if col and col not in rec:
                rec[col] = val
        out.append((i, rec))
    return out


def _errors(exc: ValidationError) -> list[str]:
    msgs = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", ()) if x != "__root__")
        msg = e.get("msg", "invalid").removeprefix("Value error, ")
        msgs.append(f"{loc}: {msg}" if loc else msg)
    return msgs


def process_import(db: Session, user_id: uuid.UUID, rows: list[tuple[int, dict[str, str]]], commit: bool) -> dict:
    existing = {
        d: cid
        for cid, d in db.execute(select(Company.id, Company.normalized_domain).where(Company.user_id == user_id))
    }
    seen_in_file: dict[str, int] = {}
    results: list[dict] = []
    created: list[str] = []
    summary = {"total": len(rows), "valid": 0, "duplicates": 0, "invalid": 0}

    for rownum, rec in rows:
        item: dict[str, Any] = {
            "row": rownum,
            "status": "valid",
            "normalized_domain": None,
            "errors": [],
            "existing_company_id": None,
            "data": rec,
        }
        try:
            payload = CompanyCreate(**{k: (v or None) for k, v in rec.items()})
        except ValidationError as exc:
            item["status"] = "invalid"
            item["errors"] = _errors(exc)
            summary["invalid"] += 1
            results.append(item)
            continue

        domain = normalize_website(payload.website_url).domain
        item["normalized_domain"] = domain
        if domain in existing:
            item["status"] = "duplicate"
            item["existing_company_id"] = str(existing[domain])
            item["errors"] = ["A company with this domain already exists"]
            summary["duplicates"] += 1
        elif domain in seen_in_file:
            item["status"] = "duplicate"
            item["errors"] = [f"Duplicate of row {seen_in_file[domain]} in this file"]
            summary["duplicates"] += 1
        else:
            seen_in_file[domain] = rownum
            if commit:
                company = Company(user_id=user_id, normalized_domain=domain, **payload.model_dump())
                try:
                    with db.begin_nested():
                        db.add(company)
                        db.flush()
                    created.append(str(company.id))
                    item["created_company_id"] = str(company.id)
                except IntegrityError:
                    item["status"] = "duplicate"
                    item["errors"] = ["A company with this domain already exists"]
                    summary["duplicates"] += 1
                    results.append(item)
                    continue
            summary["valid"] += 1
        results.append(item)

    if commit:
        db.commit()
    return {
        "mode": "commit" if commit else "preview",
        "summary": summary,
        "rows": results,
        "created_company_ids": created,
    }
