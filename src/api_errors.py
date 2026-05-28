"""Framework-agnostic domain error hierarchy.

These exceptions carry an HTTP-style ``status_code`` so the FastAPI layer can
translate them into responses, but they intentionally avoid importing FastAPI.
The desktop runtime (packaged exe) reuses ``CVMReadService`` without bundling
FastAPI, so error types raised on the shared read/refresh codepath must live in
``src/`` and stay import-light.
"""

from __future__ import annotations

from dataclasses import dataclass

HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_CONTENT = 422
HTTP_SERVICE_UNAVAILABLE = 503


@dataclass(frozen=True)
class ApiError(Exception):
    status_code: int
    code: str
    message: str


class NotFoundError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=HTTP_NOT_FOUND,
            code="not_found",
            message=message,
        )


class ServiceUnavailableError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=HTTP_SERVICE_UNAVAILABLE,
            code="service_unavailable",
            message=message,
        )


class InvalidRequestError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=HTTP_UNPROCESSABLE_CONTENT,
            code="invalid_request",
            message=message,
        )
