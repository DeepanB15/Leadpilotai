from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: Any = None, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class ValidationFailed(AppError):
    status_code = 400
    code = "validation_error"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Duplicate(AppError):
    status_code = 409
    code = "duplicate"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class FileTooLarge(AppError):
    status_code = 413
    code = "file_too_large"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"


def error_body(code: str, message: str, details: Any = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id_var.get(),
        }
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
        ]
        return JSONResponse(status_code=400, content=error_body("validation_error", "Invalid request", details))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {401: "unauthorized", 404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        import logging

        logging.getLogger("app").exception("unhandled error")
        return JSONResponse(status_code=500, content=error_body("internal_error", "Internal server error"))
