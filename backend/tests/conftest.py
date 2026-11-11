import os
import tempfile
import time
import uuid

_tmp = tempfile.mkdtemp(prefix="leadpilot-test-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["SUPABASE_JWT_SECRET"] = "test-secret-test-secret-test-secret-12345"
os.environ["DOMAIN_MIN_INTERVAL_SECONDS"] = "0"
os.environ["RESPECT_ROBOTS_TXT"] = "true"

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import rate_limit  # noqa: E402

USER_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


def make_token(user_id: uuid.UUID, *, secret: str | None = None, exp_delta: int = 3600, aud: str = "authenticated") -> str:
    return jwt.encode(
        {"sub": str(user_id), "aud": aud, "exp": int(time.time()) + exp_delta, "email": "t@example.com"},
        secret or os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    rate_limit.reset()
    yield


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_a():
    return {"Authorization": f"Bearer {make_token(USER_A)}"}


@pytest.fixture()
def auth_b():
    return {"Authorization": f"Bearer {make_token(USER_B)}"}
