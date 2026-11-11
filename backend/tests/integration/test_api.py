import io
import uuid

from openpyxl import Workbook

from app.models import Company
from tests.conftest import USER_A, USER_B, make_token


def mk(client, auth, name="Acme", site="acme.com", **extra):
    return client.post("/api/v1/companies", json={"name": name, "website_url": site, **extra}, headers=auth)


# ----------------------------------------------------------------------- auth
def test_health_is_public(client):
    assert client.get("/api/v1/health").json() == {"status": "ok", "database": "ok"}
    assert client.get("/health").status_code == 200


def test_protected_endpoints_require_valid_token(client):
    assert client.get("/api/v1/companies").status_code == 401
    assert client.get("/api/v1/companies", headers={"Authorization": "Bearer garbage"}).status_code == 401
    bad_secret = make_token(USER_A, secret="wrong-secret-wrong-secret-wrong-secret-1")
    assert client.get("/api/v1/companies", headers={"Authorization": f"Bearer {bad_secret}"}).status_code == 401
    expired = make_token(USER_A, exp_delta=-10)
    assert client.get("/api/v1/companies", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    wrong_aud = make_token(USER_A, aud="other")
    assert client.get("/api/v1/companies", headers={"Authorization": f"Bearer {wrong_aud}"}).status_code == 401
    r = client.get("/api/v1/companies")
    assert r.json()["error"]["code"] == "unauthorized" and r.headers["x-request-id"]


def test_user_id_in_body_is_ignored(client, auth_a, db):
    r = mk(client, auth_a, user_id=str(USER_B))
    assert r.status_code == 201
    assert db.get(Company, uuid.UUID(r.json()["id"])).user_id == USER_A


# ------------------------------------------------------------------ companies
def test_company_crud_and_normalization(client, auth_a):
    r = mk(client, auth_a, name="  Acme   Software ", site="HTTP://www.Acme.com/", linkedin_url="linkedin.com/company/acme")
    assert r.status_code == 201
    c = r.json()
    assert c["name"] == "Acme Software" and c["normalized_domain"] == "acme.com"
    assert c["linkedin_url"] == "https://www.linkedin.com/company/acme" and c["latest_status"] is None

    assert client.get(f"/api/v1/companies/{c['id']}", headers=auth_a).json()["id"] == c["id"]
    up = client.patch(f"/api/v1/companies/{c['id']}", json={"industry": "Software", "linkedin_url": None}, headers=auth_a)
    assert up.status_code == 200 and up.json()["industry"] == "Software" and up.json()["linkedin_url"] is None
    lst = client.get("/api/v1/companies?q=acme", headers=auth_a).json()
    assert lst["total"] == 1 and lst["items"][0]["id"] == c["id"]
    assert client.get("/api/v1/companies?q=zzz", headers=auth_a).json()["total"] == 0
    assert client.get("/api/v1/companies?status=pending", headers=auth_a).json()["total"] == 1
    assert client.delete(f"/api/v1/companies/{c['id']}", headers=auth_a).status_code == 204
    assert client.get(f"/api/v1/companies/{c['id']}", headers=auth_a).status_code == 404


def test_validation_errors(client, auth_a):
    for body in (
        {"name": "", "website_url": "acme.com"},
        {"name": "X", "website_url": "http://127.0.0.1"},
        {"name": "X", "website_url": "ftp://acme.com"},
        {"name": "X", "website_url": "acme.com", "linkedin_url": "instagram.com/acme"},
        {"name": "X"},
    ):
        r = client.post("/api/v1/companies", json=body, headers=auth_a)
        assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error", body


def test_duplicate_domain_detected_per_user(client, auth_a, auth_b):
    first = mk(client, auth_a).json()
    dup = mk(client, auth_a, name="Acme 2", site="https://www.acme.com/contact")
    assert dup.status_code == 409 and dup.json()["error"]["details"]["existing_company_id"] == first["id"]
    assert mk(client, auth_b).status_code == 201  # same domain, different user is fine


def test_ownership_is_enforced_everywhere(client, auth_a, auth_b):
    cid = mk(client, auth_a).json()["id"]
    job = client.post(f"/api/v1/companies/{cid}/research", headers=auth_a).json()["job_id"]
    for method, path in [
        ("get", f"/api/v1/companies/{cid}"), ("patch", f"/api/v1/companies/{cid}"), ("delete", f"/api/v1/companies/{cid}"),
        ("get", f"/api/v1/companies/{cid}/sources"), ("get", f"/api/v1/companies/{cid}/profile"),
        ("get", f"/api/v1/companies/{cid}/findings"), ("get", f"/api/v1/companies/{cid}/reports"),
        ("post", f"/api/v1/companies/{cid}/research"), ("get", f"/api/v1/research/jobs/{job}"),
        ("post", f"/api/v1/research/jobs/{job}/cancel"), ("post", f"/api/v1/research/jobs/{job}/retry"),
        ("get", f"/api/v1/reports/{uuid.uuid4()}"),
    ]:
        kw = {"json": {}} if method == "patch" else {}
        r = getattr(client, method)(path, headers=auth_b, **kw)
        assert r.status_code == 404, (method, path, r.status_code)
    assert client.get("/api/v1/companies", headers=auth_b).json()["total"] == 0
    assert client.get("/api/v1/research/jobs", headers=auth_b).json()["total"] == 0
    assert client.get("/api/v1/dashboard/stats", headers=auth_b).json()["total"] == 0


def test_delete_blocked_while_research_active(client, auth_a):
    cid = mk(client, auth_a).json()["id"]
    client.post(f"/api/v1/companies/{cid}/research", headers=auth_a)
    assert client.delete(f"/api/v1/companies/{cid}", headers=auth_a).status_code == 409


def test_companies_csv_export(client, auth_a):
    mk(client, auth_a)
    r = client.get("/api/v1/companies/export/csv", headers=auth_a)
    assert r.status_code == 200 and "acme.com" in r.text and r.headers["content-type"].startswith("text/csv")


# --------------------------------------------------------------------- import
CSV = (
    "company_name,website,linkedin_url,industry\n"
    "Acme Software,acme.com,linkedin.com/company/acme,Software\n"
    "NovaTech,https://novatech.com,,\n"
    "Acme Again,www.acme.com/about,,\n"       # duplicate of row 2 (in file)
    "Bad Url,http://10.0.0.1,,\n"              # invalid
    ",nameless.com,,\n"                         # invalid
    "Bad Social,badsocial.com,instagram.com/x,\n"  # invalid (wrong platform)
)


def post_csv(client, auth, content, mode="preview", name="c.csv"):
    return client.post(f"/api/v1/imports/csv?mode={mode}", files={"file": (name, content, "text/csv")}, headers=auth)


def test_csv_import_preview_then_commit(client, auth_a):
    p = post_csv(client, auth_a, CSV).json()
    assert p["summary"] == {"total": 6, "valid": 2, "duplicates": 1, "invalid": 3}
    assert [r["status"] for r in p["rows"]] == ["valid", "valid", "duplicate", "invalid", "invalid", "invalid"]
    assert client.get("/api/v1/companies", headers=auth_a).json()["total"] == 0  # preview saves nothing

    c = post_csv(client, auth_a, CSV, "commit").json()
    assert len(c["created_company_ids"]) == 2
    assert client.get("/api/v1/companies", headers=auth_a).json()["total"] == 2
    again = post_csv(client, auth_a, CSV, "commit").json()  # re-import: existing become duplicates
    assert again["summary"]["valid"] == 0 and again["summary"]["duplicates"] == 3 and not again["created_company_ids"]


def test_csv_accepts_header_aliases_and_bom(client, auth_a):
    content = "﻿Company,URL\nZed Corp,zed.io\n".encode()
    r = post_csv(client, auth_a, content, "commit")
    assert r.status_code == 200 and len(r.json()["created_company_ids"]) == 1


def test_csv_missing_columns_and_bad_files(client, auth_a):
    r = post_csv(client, auth_a, "foo,bar\n1,2\n")
    assert r.status_code == 400 and "company_name" in r.json()["error"]["message"]
    assert post_csv(client, auth_a, "").status_code == 400
    assert post_csv(client, auth_a, CSV, name="c.exe").status_code == 400
    big = "company_name,website\n" + "".join(f"C{i},c{i}.com\n" for i in range(1001))
    assert post_csv(client, auth_a, big).status_code == 400


def test_excel_import(client, auth_a):
    wb = Workbook()
    ws = wb.active
    ws.append(["company_name", "website", "industry"])
    ws.append(["Xl One", "xlone.com", "Retail"])
    ws.append(["Xl Bad", "nope", None])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/api/v1/imports/excel?mode=commit", files={"file": ("a.xlsx", buf.getvalue(), "application/octet-stream")}, headers=auth_a)
    assert r.status_code == 200 and r.json()["summary"] == {"total": 2, "valid": 1, "duplicates": 0, "invalid": 1}
    bad = client.post("/api/v1/imports/excel", files={"file": ("a.xlsx", b"not a workbook", "application/octet-stream")}, headers=auth_a)
    assert bad.status_code == 400


# ------------------------------------------------------------------- research
def test_research_lifecycle_endpoints(client, auth_a):
    cid = mk(client, auth_a).json()["id"]
    r = client.post(f"/api/v1/companies/{cid}/research", headers=auth_a)
    assert r.status_code == 202 and r.json()["status"] == "queued"
    jid = r.json()["job_id"]
    assert client.post(f"/api/v1/companies/{cid}/research", headers=auth_a).status_code == 409
    assert client.get(f"/api/v1/companies/{cid}", headers=auth_a).json()["latest_status"] == "queued"
    assert client.get("/api/v1/dashboard/stats", headers=auth_a).json()["processing"] == 1

    job = client.get(f"/api/v1/research/jobs/{jid}", headers=auth_a).json()
    assert job["status"] == "queued" and job["company_name"] == "Acme"
    assert client.post(f"/api/v1/research/jobs/{jid}/retry", headers=auth_a).status_code == 409  # still active
    assert client.post(f"/api/v1/research/jobs/{jid}/cancel", headers=auth_a).json()["status"] == "cancelled"
    assert client.post(f"/api/v1/research/jobs/{jid}/cancel", headers=auth_a).status_code == 409
    retry = client.post(f"/api/v1/research/jobs/{jid}/retry", headers=auth_a)
    assert retry.status_code == 202 and retry.json()["job_id"] != jid
    assert client.get("/api/v1/research/jobs?status=queued", headers=auth_a).json()["total"] == 1


def test_batch_isolates_failures(client, auth_a):
    a = mk(client, auth_a, "A", "a.com").json()["id"]
    b = mk(client, auth_a, "B", "b.com").json()["id"]
    client.post(f"/api/v1/companies/{a}/research", headers=auth_a)
    ghost = str(uuid.uuid4())
    res = client.post("/api/v1/research/batch", json={"company_ids": [a, b, ghost, b]}, headers=auth_a).json()["jobs"]
    by = {j["company_id"]: j for j in res}
    assert by[a]["error"] == "already_in_progress" and by[b]["status"] == "queued" and by[ghost]["error"] == "not_found"
    assert len(res) == 3
    assert client.post("/api/v1/research/batch", json={"company_ids": []}, headers=auth_a).status_code == 400


def test_import_rate_limit(client, auth_a):
    codes = [post_csv(client, auth_a, "company_name,website\nA,a.com\n").status_code for _ in range(7)]
    assert 429 in codes
