from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import httpx

from .errors import TraceportError

DEFAULT_BASE_URL = "https://api.traceport.ai/v1"


def positive(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise TypeError(f"{name} must be a finite positive number of seconds")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value <= 0:
        raise TypeError(f"{name} must be a finite positive number of seconds")
    return float(value)


def retries(value: int) -> int:
    if type(value) is not int or value < 0:
        raise TypeError("max_retries must be a non-negative integer")
    return value


def extra_headers(value: Mapping[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("headers must be a mapping of strings")
    result = dict(value)
    for key, item in result.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise TypeError("headers must map strings to strings")
        try:
            httpx.Headers({key: item})
        except (ValueError, UnicodeError) as exc:
            raise TypeError("headers must contain valid HTTP header values") from exc
    return result


@dataclass(frozen=True)
class ClientConfig:
    api_key: str
    base_url: str
    timeout: float
    max_retries: int
    headers: Mapping[str, str]


def configuration(
    *,
    api_key: str | None,
    base_url: str | None,
    timeout: float,
    max_retries: int,
    default_headers: Mapping[str, str] | None,
) -> ClientConfig:
    key = api_key if api_key is not None else os.environ.get("TRACEPORT_API_KEY", "")
    if not isinstance(key, str):
        raise TypeError("api_key must be a string")
    key = key.strip()
    if not key:
        raise TraceportError("missing API key: pass api_key or set TRACEPORT_API_KEY")
    if any(ord(char) < 32 or ord(char) == 127 for char in key):
        raise TypeError("api_key must not contain control characters")
    url = base_url if base_url is not None else os.environ.get("TRACEPORT_BASE_URL", "").strip()
    if not url and base_url is None:
        url = DEFAULT_BASE_URL
    if not isinstance(url, str):
        raise TypeError("base_url must be a string")
    url = url.rstrip("/")
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise TypeError("base_url must be an absolute HTTP(S) URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.host
        or parsed.query
        or parsed.fragment
        or parsed.userinfo
    ):
        raise TypeError(
            "base_url must be an absolute HTTP(S) URL without credentials/query/fragment"
        )
    return ClientConfig(
        api_key=key,
        base_url=url,
        timeout=positive(timeout, "timeout"),
        max_retries=retries(max_retries),
        headers=MappingProxyType(extra_headers(default_headers)),
    )
