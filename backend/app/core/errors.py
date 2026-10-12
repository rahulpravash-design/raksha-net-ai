"""Application error hierarchy and the handlers that render it.

Every error crossing the API boundary becomes the same JSON envelope, so
clients have one shape to parse. Internal details never reach the client; they
go to the log with the request id that the client also holds.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import metrics
from app.core.logging import get_logger, request_id_var

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for every expected, client-visible failure."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "APP_ERROR"
    message: str = "Request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        self.status_code = status_code or self.status_code
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        request_id = request_id_var.get()
        if request_id:
            error["request_id"] = request_id
        return {"error": error}


# --- 400 ---------------------------------------------------------------------
class ValidationError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "VALIDATION_ERROR"
    message = "The request contained invalid data."


class InvalidCoordinatesError(ValidationError):
    code = "INVALID_COORDINATES"
    message = "The supplied coordinates are not valid for this deployment."


class InvalidResetTokenError(ValidationError):
    """One answer for unknown, expired, used and replaced links, so the response
    reveals nothing about which it was."""

    code = "INVALID_RESET_TOKEN"
    message = "This recovery link is invalid or has expired. Request a new one."


class PasswordUnchangedError(ValidationError):
    code = "PASSWORD_UNCHANGED"
    message = "The new password must be different from the current one."


class WeakPasswordError(ValidationError):
    code = "WEAK_PASSWORD"
    message = "The password does not meet the minimum requirements."


# --- 401 ---------------------------------------------------------------------
class NotAuthenticatedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "NOT_AUTHENTICATED"
    message = "Authentication is required."


class InvalidCredentialsError(NotAuthenticatedError):
    code = "INVALID_CREDENTIALS"
    message = "Incorrect email or password."


class InvalidTokenError(NotAuthenticatedError):
    code = "INVALID_TOKEN"
    message = "The token is invalid or has expired."


class InactiveAccountError(NotAuthenticatedError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "ACCOUNT_INACTIVE"
    message = "This account has been deactivated."


class AccountLockedError(NotAuthenticatedError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "ACCOUNT_LOCKED"
    message = "Too many failed sign-in attempts. Try again later."

    def __init__(self, *, retry_after_seconds: int, **kwargs: Any) -> None:
        super().__init__(details={"retry_after_seconds": retry_after_seconds}, **kwargs)


class MfaEnrollmentRequiredError(NotAuthenticatedError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "MFA_ENROLLMENT_REQUIRED"
    message = (
        "Multi-factor authentication must be set up for this account "
        "before it can be used."
    )


class PasswordChangeRequiredError(NotAuthenticatedError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "PASSWORD_CHANGE_REQUIRED"
    message = (
        "This account's password was set by an administrator and must be "
        "changed before anything else can be done."
    )


class MfaRequiredError(NotAuthenticatedError):
    code = "MFA_REQUIRED"
    message = "A verification code from your authenticator app is required."


class InvalidMfaCodeError(NotAuthenticatedError):
    code = "INVALID_MFA_CODE"
    message = "That verification code is incorrect or has expired."


# --- 403 / 404 ---------------------------------------------------------------
class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    message = "You do not have permission to perform this action."


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "The requested resource was not found."


# --- 409 ---------------------------------------------------------------------
class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    message = "The request conflicts with the current state."


class EmailAlreadyRegisteredError(ConflictError):
    code = "EMAIL_ALREADY_REGISTERED"
    message = "An account with this email address already exists."


class AdminAlreadyExistsError(ConflictError):
    code = "ADMIN_ALREADY_EXISTS"
    message = (
        "An administrator account already exists, so no first administrator "
        "can be created."
    )


class InvalidStatusTransitionError(ConflictError):
    code = "INCIDENT_INVALID_TRANSITION"
    message = "That status change is not permitted from the current status."


class AnalysisAlreadyReviewedError(ConflictError):
    code = "ANALYSIS_ALREADY_REVIEWED"
    message = "This AI analysis has already been reviewed."


# --- 422 -----------------------------------------------------------------
class AnalysisRejectedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "ANALYSIS_REJECTED"
    message = "The AI analysis output failed validation and was discarded."


# --- 413 / 415 / 429 ---------------------------------------------------------
class MediaTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "MEDIA_TOO_LARGE"
    message = "The uploaded file exceeds the maximum allowed size."


class UnsupportedMediaTypeError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "MEDIA_UNSUPPORTED_TYPE"
    message = "That file type is not accepted."


class MediaInfectedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "MEDIA_INFECTED"
    message = "The file was rejected because it was flagged as malicious."


class MediaScanUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "MEDIA_SCAN_UNAVAILABLE"
    message = "Uploads cannot be accepted right now because they cannot be scanned."


class ServiceBusyError(AppError):
    """Shed load honestly: tell the client to retry rather than hang it."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SERVICE_BUSY"
    message = "The system is very busy. Please try again in a moment."

    def __init__(
        self, message: str | None = None, *, retry_after: int = 1, **kwargs: Any
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class DatabaseUnavailableError(AppError):
    """The database could not be reached or dropped the connection.

    Distinct from a bug (500): the request was fine and retrying later can succeed,
    which is what a client, a load balancer and an operator each need to be told.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"
    message = "The service is temporarily unavailable. Please try again shortly."


class AnalysisUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "ANALYSIS_UNAVAILABLE"
    message = (
        "AI analysis is not available right now. "
        "The incident remains fully usable from the reporter's own words."
    )


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    message = "Too many requests. Please slow down."

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after: int = 60,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers that produce the documented error envelope."""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitedError | ServiceBusyError):
            headers["Retry-After"] = str(exc.retry_after)
        logger.info(
            "request_rejected",
            extra={"error_code": exc.code, "status_code": exc.status_code},
        )
        return JSONResponse(
            status_code=exc.status_code, content=exc.to_payload(), headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(part) for part in err["loc"][1:]) or "body",
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        error = ValidationError(details={"fields": fields})
        return JSONResponse(status_code=error.status_code, content=error.to_payload())

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        mapped = AppError(
            message=str(exc.detail),
            code=_code_for_status(exc.status_code),
            status_code=exc.status_code,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=mapped.to_payload(),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(SQLAlchemyTimeoutError)
    async def _pool_exhausted(_: Request, exc: SQLAlchemyTimeoutError) -> JSONResponse:
        # Every connection stayed busy for the whole pool timeout. That is
        # overload, not a bug in the request: say so, and say when to retry.
        metrics.DB_POOL_EXHAUSTED.inc()
        logger.error("database_pool_exhausted", extra={"detail": str(exc)[:200]})
        busy = ServiceBusyError(retry_after=2)
        return JSONResponse(
            status_code=busy.status_code,
            content=busy.to_payload(),
            headers={"Retry-After": str(busy.retry_after)},
        )

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def _database_unavailable(
        _: Request, exc: OperationalError | InterfaceError
    ) -> JSONResponse:
        # Connection refused, host unreachable, server restarting, dropped mid-query.
        # The driver's message can name the database host, so it goes to the log only.
        logger.error(
            "database_unavailable",
            extra={
                "error_type": type(exc.orig or exc).__name__,
                "detail": str(exc.orig)[:200],
            },
        )
        unavailable = DatabaseUnavailableError()
        return JSONResponse(
            status_code=unavailable.status_code,
            content=unavailable.to_payload(),
            headers={"Retry-After": "5"},
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Log the detail; return none of it.
        logger.exception("unhandled_exception", exc_info=exc)
        internal = AppError(
            message="An internal error occurred.",
            code="INTERNAL_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return JSONResponse(status_code=500, content=internal.to_payload())


def _code_for_status(status_code: int) -> str:
    return {
        401: "NOT_AUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "MEDIA_TOO_LARGE",
        415: "MEDIA_UNSUPPORTED_TYPE",
        429: "RATE_LIMITED",
    }.get(status_code, "HTTP_ERROR")
