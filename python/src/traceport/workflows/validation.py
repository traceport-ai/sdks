from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Mapping
from typing import Any

from .._core.config import positive, retries
from .._core.types import RequestOptions


def resource_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value


def mutation_body(version_id: str, input: Mapping[str, Any] | None) -> dict[str, Any]:
    if input is not None and not isinstance(input, Mapping):
        raise TypeError("input must be an object mapping strings to JSON values")
    return {
        "configVersionID": resource_id(version_id, "version_id"),
        "additional": dict(input or {}),
    }


def idempotency_key(key: str | None) -> str:
    if key is None:
        return str(uuid.uuid4())
    if not isinstance(key, str) or not key:
        raise TypeError("idempotency_key must be a string of 1-200 bytes")
    try:
        encoded = key.encode("utf-8")
    except UnicodeError as exc:
        raise TypeError("idempotency_key must be valid UTF-8") from exc
    if len(encoded) > 200:
        raise TypeError("idempotency_key must be a string of 1-200 bytes")
    if any(char.isspace() or unicodedata.category(char) == "Cc" for char in key):
        raise TypeError("idempotency_key must not contain whitespace or control characters")
    return key


def list_query(
    version_id: str | None, status: str | None, limit: int | None, offset: int | None
) -> dict[str, str | int]:
    for value, name in ((limit, "limit"), (offset, "offset")):
        if value is not None and type(value) is not int:
            raise TypeError(f"{name} must be an integer")
    return {
        key: value
        for key, value in {
            "configVersionID": version_id,
            "status": status,
            "limit": limit,
            "offset": offset,
        }.items()
        if value is not None
    }


def wait_settings(
    timeout: float,
    poll_interval: float,
    max_poll_interval: float,
    request_timeout: float | None,
    max_retries: int | None,
) -> RequestOptions:
    positive(timeout, "timeout")
    positive(poll_interval, "poll_interval")
    positive(max_poll_interval, "max_poll_interval")
    result: RequestOptions = {}
    if request_timeout is not None:
        result["timeout"] = positive(request_timeout, "request_timeout")
    if max_retries is not None:
        result["max_retries"] = retries(max_retries)
    return result
