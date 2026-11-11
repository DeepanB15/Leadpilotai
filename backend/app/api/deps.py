from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import Unauthorized
from app.core.security import AuthUser, verify_token
from app.db import get_db

bearer = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> AuthUser:
    """The user id comes only from the verified Supabase token - never from client-supplied fields."""
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise Unauthorized("Missing bearer token")
    return verify_token(creds.credentials)


__all__ = ["AuthUser", "Session", "get_current_user", "get_db"]
