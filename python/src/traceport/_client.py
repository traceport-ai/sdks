"""The shared Traceport clients.

A client owns configuration and HTTP only. Product subpackages (``traceport.workflows``, later
``traceport.documents``) take a client in their constructor and send requests through it, so one
client, configured once, serves every product.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Self, TypedDict

import httpx

from ._core.config import ClientConfig, configuration, extra_headers
from ._core.transport import AsyncTransport, Transport


class _DerivedSettings(TypedDict):
    """Keyword arguments shared by both client constructors, minus ``http_client``."""

    api_key: str
    base_url: str
    timeout: float
    max_retries: int
    default_headers: Mapping[str, str]


def _derived_settings(
    config: ClientConfig,
    timeout: float | None,
    max_retries: int | None,
    default_headers: Mapping[str, str] | None,
) -> _DerivedSettings:
    """Constructor arguments for a derived client: same key and base URL, merged headers."""
    return {
        "api_key": config.api_key,
        "base_url": config.base_url,
        "timeout": config.timeout if timeout is None else timeout,
        "max_retries": config.max_retries if max_retries is None else max_retries,
        "default_headers": {**config.headers, **extra_headers(default_headers)},
    }


class Traceport:
    """Synchronous client shared by every product. Pass it to product classes such as
    ``traceport.workflows.Workflows``.

    Use a context manager or ``close()`` to release owned connections.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60,
        max_retries: int = 2,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if http_client is not None and not isinstance(http_client, httpx.Client):
            raise TypeError("http_client must be an httpx.Client")
        config = configuration(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
        )
        self.base_url = config.base_url
        self._transport = Transport(config, http_client)

    def with_options(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        default_headers: Mapping[str, str] | None = None,
    ) -> Self:
        """Return a client with the same API key, base URL and connection pool, and different
        timeouts, retries or default headers (merged over this client's).

        Use it to give one product different settings without configuring a second client. The
        derived client borrows this client's connections and does not own them: closing it
        leaves this client open, and it stops working once this client is closed.
        """
        self._transport._check_open()
        settings = _derived_settings(self._transport.config, timeout, max_retries, default_headers)
        return type(self)(**settings, http_client=self._transport._client)

    def close(self) -> None:
        """Close owned connections. An injected HTTP client remains owned by its caller."""
        self._transport.close()

    def __enter__(self) -> Self:
        self._transport._check_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class AsyncTraceport:
    """AsyncIO client shared by every product. Pass it to async product classes such as
    ``traceport.workflows.AsyncWorkflows``.

    Use ``async with`` or ``await aclose()`` to release owned connections.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60,
        max_retries: int = 2,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if http_client is not None and not isinstance(http_client, httpx.AsyncClient):
            raise TypeError("http_client must be an httpx.AsyncClient")
        config = configuration(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
        )
        self.base_url = config.base_url
        self._transport = AsyncTransport(config, http_client)

    def with_options(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        default_headers: Mapping[str, str] | None = None,
    ) -> Self:
        """Return a client with the same API key, base URL and connection pool, and different
        timeouts, retries or default headers (merged over this client's).

        The derived client borrows this client's connections and does not own them: closing it
        leaves this client open, and it stops working once this client is closed.
        """
        self._transport._check_open()
        settings = _derived_settings(self._transport.config, timeout, max_retries, default_headers)
        return type(self)(**settings, http_client=self._transport._client)

    async def aclose(self) -> None:
        """Close owned connections. An injected HTTP client remains owned by its caller."""
        await self._transport.aclose()

    async def __aenter__(self) -> Self:
        self._transport._check_open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


def transport_of(client: Traceport) -> Transport:
    """Return a synchronous client's transport. Internal: used by product subpackages."""
    if isinstance(client, AsyncTraceport):
        raise TypeError(
            "expected traceport.Traceport; use the Async product class with AsyncTraceport"
        )
    if not isinstance(client, Traceport):
        raise TypeError("expected a traceport.Traceport client")
    return client._transport


def async_transport_of(client: AsyncTraceport) -> AsyncTransport:
    """Return an AsyncIO client's transport. Internal: used by product subpackages."""
    if isinstance(client, Traceport):
        raise TypeError(
            "expected traceport.AsyncTraceport; use the sync product class with Traceport"
        )
    if not isinstance(client, AsyncTraceport):
        raise TypeError("expected a traceport.AsyncTraceport client")
    return client._transport
