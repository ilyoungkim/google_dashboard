"""Standardised error responses for the API."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class AppError(HTTPException):
    """Base application error with a machine-readable code."""

    def __init__(self, status_code: int, code: str, message: str, detail: dict | None = None):
        super().__init__(status_code=status_code, detail=message)
        self.error_code = code
        self.error_detail = detail or {}


# ── Convenience factories ──────────────────────────────────────────────

def unauthenticated() -> AppError:
    return AppError(401, "UNAUTHENTICATED", "Session missing or expired. Please log in again.")


def token_refresh_failed() -> AppError:
    return AppError(401, "TOKEN_REFRESH_FAILED", "Refresh token is also expired. Please re-authenticate.")


def insufficient_scope() -> AppError:
    return AppError(403, "INSUFFICIENT_SCOPE", "The requested operation requires a scope that was not granted.")


def rate_limited(retry_after: int = 60) -> AppError:
    return AppError(
        429,
        "RATE_LIMITED",
        f"Too many requests. Retry after {retry_after} seconds.",
        {"retry_after": retry_after},
    )


def upstream_error(detail: str = "") -> AppError:
    return AppError(502, "UPSTREAM_ERROR", f"Google Search Console API error. {detail}".strip())


def not_found(resource: str = "Resource") -> AppError:
    return AppError(404, "NOT_FOUND", f"{resource} not found.")


# ── Exception handler registration ────────────────────────────────────

def register_error_handlers(app):
    """Attach JSON error handlers to a FastAPI *app* instance."""

    @app.exception_handler(AppError)
    async def app_error_handler(request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.detail,
                    "detail": exc.error_detail,
                }
            },
        )
