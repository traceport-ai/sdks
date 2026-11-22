from __future__ import annotations

import re
from typing import Any

import httpx

RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
_EXISTING_RUN = re.compile(
    r"inspect the original run:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*$",
    re.IGNORECASE,
)


class TraceportError(Exception):
    """Base class for SDK errors. Invalid local arguments raise TypeError."""


class APIError(TraceportError):
    """HTTP failure, retaining the response body, headers and machine-readable error code."""

    def __init__(
        self,
        message: str,
        *,
        status: int,
        error_code: str = "",
        headers: httpx.Headers | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error_code = error_code
        self.headers = httpx.Headers(headers)
        self.body = body
        self.request_id = self.headers.get("x-request-id")

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE_STATUSES


class BadRequestError(APIError):
    """400: invalid request or query parameter."""


class AuthenticationError(APIError):
    """401: missing, unknown, inactive or expired key."""


class PaymentRequiredError(APIError):
    """402: insufficient wallet credits."""


class PermissionDeniedError(APIError):
    """403: plan or allowance restriction."""


class NotFoundError(APIError):
    """404: resource missing or owned by another organization."""


class ConflictError(APIError):
    """409: idempotency, in-progress replay or workflow revision conflict."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        match = _EXISTING_RUN.search(message)
        self.existing_run_id = match.group(1) if match else None


class RateLimitError(APIError):
    """429: rate limited; retries honor Retry-After."""


class InternalServerError(APIError):
    """5xx: server failure. Retryable identifies the transient subset."""


class APIConnectionError(TraceportError):
    """A connection or response-body I/O failure. The original cause is chained."""


class APITimeoutError(APIConnectionError):
    """A request attempt exceeded its timeout."""


class RequestAbortedError(TraceportError):
    """The supplied cancellation event was set. Never retried."""


class InvalidResponseError(TraceportError):
    """A successful HTTP response has an invalid envelope or resource."""

    def __init__(self, message: str, *, status: int, body: Any) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def api_error(status: int, headers: httpx.Headers, body: Any) -> APIError:
    envelope = body if isinstance(body, dict) else {}
    message = envelope.get("error")
    if not isinstance(message, str) or not message.strip():
        message = f"request failed with HTTP {status}"
    code = envelope.get("errorCode", "")
    if not isinstance(code, str):
        code = ""
    error_type = {
        400: BadRequestError,
        401: AuthenticationError,
        402: PaymentRequiredError,
        403: PermissionDeniedError,
        404: NotFoundError,
        409: ConflictError,
        429: RateLimitError,
    }.get(status, InternalServerError if status >= 500 else APIError)
    return error_type(message, status=status, error_code=code, headers=headers, body=body)


class _ObservationExpired(Exception):
    """Internal transport deadline, translated to a workflow WaitTimeoutError."""
