"""Traceport Python SDK: the shared clients, request options and request errors.

Create one client and pass it to each product you use::

    from traceport import Traceport
    from traceport.workflows import Workflows

    client = Traceport()  # reads TRACEPORT_API_KEY
    workflows = Workflows(client)

Products live in subpackages (``traceport.workflows``, later ``traceport.documents``); each takes
the same client, so credentials, base URL, timeouts and retries are configured once.
"""

from ._client import AsyncTraceport, Traceport
from ._core.config import DEFAULT_BASE_URL
from ._core.errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    InvalidResponseError,
    NotFoundError,
    PaymentRequiredError,
    PermissionDeniedError,
    RateLimitError,
    RequestAbortedError,
    TraceportError,
)
from ._core.types import RequestOptions
from ._version import __version__

__all__ = [
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "AsyncTraceport",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "DEFAULT_BASE_URL",
    "InternalServerError",
    "InvalidResponseError",
    "NotFoundError",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "RateLimitError",
    "RequestAbortedError",
    "RequestOptions",
    "Traceport",
    "TraceportError",
    "__version__",
]
