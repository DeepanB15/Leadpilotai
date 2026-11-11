"""Supabase access-token verification.

Supports HS256 (project JWT secret) and asymmetric keys (RS256/ES256 via the
project's JWKS endpoint). The user id is taken from the verified ``sub`` claim only.
"""

import uuid
from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.core.config import get_settings
from app.core.errors import Unauthorized

ASYMMETRIC_ALGS = ["RS256", "ES256"]


@dataclass(frozen=True)
class AuthUser:
    id: uuid.UUID
    email: str | None = None


@lru_cache
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=3600)


def verify_token(token: str) -> AuthUser:
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid token") from exc

    alg = header.get("alg")
    try:
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise Unauthorized("Token verification is not configured")
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_audience,
                options={"require": ["exp", "sub"]},
            )
        elif alg in ASYMMETRIC_ALGS:
            url = settings.jwks_url
            if not url:
                raise Unauthorized("Token verification is not configured")
            key = _jwks_client(url).get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=ASYMMETRIC_ALGS,
                audience=settings.supabase_jwt_audience,
                options={"require": ["exp", "sub"]},
            )
        else:
            raise Unauthorized("Unsupported token algorithm")
    except Unauthorized:
        raise
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid or expired token") from exc

    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (ValueError, KeyError) as exc:
        raise Unauthorized("Invalid token subject") from exc
    return AuthUser(id=user_id, email=claims.get("email"))
