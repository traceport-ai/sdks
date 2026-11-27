from __future__ import annotations

import asyncio
import json
import math
import queue
import random
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .._version import __version__
from .config import ClientConfig, extra_headers, positive, retries
from .errors import (
    APIConnectionError,
    APITimeoutError,
    InvalidResponseError,
    RequestAbortedError,
    TraceportError,
    _ObservationExpired,
    api_error,
)
from .types import RequestOptions


@dataclass(frozen=True)
class Response:
    data: Any
    status: int
    headers: httpx.Headers


@dataclass(frozen=True)
class _Prepared:
    method: str
    url: str
    headers: httpx.Headers
    body: bytes | None
    timeout: float
    max_retries: int
    cancel_event: threading.Event | None


def check_active(cancel_event: threading.Event | None, deadline: float | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise RequestAbortedError("request was aborted")
    if deadline is not None and time.monotonic() >= deadline:
        raise _ObservationExpired


def _backoff(attempt: int) -> float:
    base = 8.0 if attempt >= 4 else 0.5 * 2**attempt
    return base * (1 - random.random() * 0.25)


def _retry_delay(headers: httpx.Headers, attempt: int) -> float:
    header = headers.get("retry-after")
    if header is not None:
        try:
            seconds = float(header)
        except ValueError:
            try:
                date = parsedate_to_datetime(header)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=UTC)
                seconds = (date - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                seconds = -1
        if math.isfinite(seconds) and seconds >= 0:
            return min(seconds, 60.0)
    return _backoff(attempt)


def sleep_sync(delay: float, cancel_event: threading.Event | None, deadline: float | None) -> None:
    check_active(cancel_event, deadline)
    if deadline is not None:
        delay = min(delay, max(0.0, deadline - time.monotonic()))
    if cancel_event is None:
        time.sleep(delay)
    else:
        cancel_event.wait(delay)
    check_active(cancel_event, deadline)


async def sleep_async(
    delay: float, cancel_event: threading.Event | None, deadline: float | None
) -> None:
    check_active(cancel_event, deadline)
    end = time.monotonic() + delay
    if deadline is not None:
        end = min(end, deadline)
    while (remaining := end - time.monotonic()) > 0:
        await asyncio.sleep(min(remaining, 0.05) if cancel_event is not None else remaining)
        check_active(cancel_event, deadline)


def _body(raw: bytes) -> Any:
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        return raw.decode("utf-8", errors="replace")


def _success(status: int, headers: httpx.Headers, body: Any) -> Response:
    if not isinstance(body, dict) or "data" not in body:
        raise InvalidResponseError(
            "response is not a Traceport API envelope", status=status, body=body
        )
    if isinstance(body.get("error"), str) and body["error"].strip():
        raise InvalidResponseError("success response reported an error", status=status, body=body)
    return Response(body["data"], status, headers)


class _BaseTransport:
    def __init__(self, config: ClientConfig) -> None:
        self.config = config
        self._closed = threading.Event()

    def _check_open(self) -> None:
        if self._closed.is_set():
            raise TraceportError("client is closed")

    def validate_options(self, options: RequestOptions) -> None:
        if "timeout" in options:
            positive(options["timeout"], "timeout")
        if "max_retries" in options:
            retries(options["max_retries"])
        extra_headers(options.get("headers"))
        event = options.get("cancel_event")
        if event is not None and not isinstance(event, threading.Event):
            raise TypeError("cancel_event must be a threading.Event")

    def _prepare(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str | int] | None,
        body: Any,
        idempotency_key: str | None,
        minimum_timeout: float,
        options: RequestOptions,
    ) -> _Prepared:
        self._check_open()
        self.validate_options(options)
        timeout = options.get("timeout", max(self.config.timeout, minimum_timeout))
        headers = httpx.Headers(
            {"Accept": "application/json", "User-Agent": f"traceport-python/{__version__}"},
            encoding="utf-8",
        )
        for source in (self.config.headers, extra_headers(options.get("headers"))):
            for key, value in source.items():
                if key.lower() not in {"authorization", "idempotency-key"}:
                    headers[key] = value
        headers["Authorization"] = f"Bearer {self.config.api_key}"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        raw: bytes | None = None
        if body is not None:
            try:
                raw = json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise TypeError("input must contain JSON-serializable values") from exc
            headers["Content-Type"] = "application/json"
        url = httpx.URL(self.config.base_url + path)
        if query:
            url = url.copy_merge_params(query)
        return _Prepared(
            method,
            str(url),
            headers,
            raw,
            timeout,
            options.get("max_retries", self.config.max_retries),
            options.get("cancel_event"),
        )

    def _request(
        self, client: httpx.Client | httpx.AsyncClient, prepared: _Prepared, timeout: float
    ) -> httpx.Request:
        request = client.build_request(
            prepared.method,
            prepared.url,
            headers=prepared.headers,
            content=prepared.body,
            timeout=timeout,
        )
        request.headers.encoding = "utf-8"
        # An injected client may have its own default credentials/headers; SDK keys always win.
        request.headers["Authorization"] = f"Bearer {self.config.api_key}"
        if "Idempotency-Key" in prepared.headers:
            request.headers["Idempotency-Key"] = prepared.headers["Idempotency-Key"]
        else:
            request.headers.pop("Idempotency-Key", None)
        return request


class Transport(_BaseTransport):
    """Sync transport with an absolute attempt budget, including response-body I/O."""

    def __init__(self, config: ClientConfig, client: httpx.Client | None = None) -> None:
        super().__init__(config)
        self._client = client if client is not None else httpx.Client(timeout=None)
        self._owns_client = client is None

    def close(self) -> None:
        if not self._closed.is_set():
            self._closed.set()
            if self._owns_client:
                self._client.close()

    def _send(
        self, prepared: _Prepared, deadline: float | None
    ) -> tuple[int, httpx.Headers, bytes]:
        check_active(prepared.cancel_event, deadline)
        expiry = time.monotonic() + prepared.timeout
        if deadline is not None:
            expiry = min(expiry, deadline)
        budget = max(0.0, expiry - time.monotonic())
        stopped = threading.Event()
        results: queue.Queue[
            tuple[tuple[int, httpx.Headers, bytes] | None, BaseException | None]
        ] = queue.Queue(1)

        def send() -> None:
            try:
                request = self._request(self._client, prepared, budget)
                response = self._client.send(
                    request, stream=True, auth=None, follow_redirects=False
                )
                try:
                    chunks: list[bytes] = []
                    if stopped.is_set():
                        raise APITimeoutError("request observation ended")
                    for chunk in response.iter_bytes():
                        if stopped.is_set() or time.monotonic() >= expiry:
                            raise APITimeoutError("request timed out while reading its body")
                        chunks.append(chunk)
                    result = (
                        response.status_code,
                        httpx.Headers(response.headers),
                        b"".join(chunks),
                    )
                finally:
                    response.close()
                results.put((result, None))
            except BaseException as exc:
                results.put((None, exc))

        # HTTPX's native timeouts are per network phase. A daemon worker bounds the caller's
        # complete attempt; native timeouts and chunk checks let abandoned I/O close promptly.
        worker = threading.Thread(target=send, name="traceport-http", daemon=True)
        worker.start()
        try:
            while True:
                self._check_open()
                check_active(prepared.cancel_event, deadline)
                remaining = expiry - time.monotonic()
                if remaining <= 0:
                    raise APITimeoutError(f"request timed out after {prepared.timeout} seconds")
                try:
                    result, error = results.get(timeout=min(remaining, 0.05))
                except queue.Empty:
                    continue
                check_active(prepared.cancel_event, deadline)
                if time.monotonic() >= expiry:
                    raise APITimeoutError(f"request timed out after {prepared.timeout} seconds")
                if error is not None:
                    if isinstance(error, httpx.TimeoutException):
                        raise APITimeoutError("HTTP request timed out") from error
                    if isinstance(error, httpx.RequestError):
                        raise APIConnectionError(
                            "could not connect to the Traceport API"
                        ) from error
                    raise error
                assert result is not None
                return result
        finally:
            stopped.set()

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str | int] | None = None,
        body: Any = None,
        idempotency_key: str | None = None,
        minimum_timeout: float = 0,
        retry_on_timeout: bool = True,
        options: RequestOptions | None = None,
        deadline: float | None = None,
    ) -> Response:
        prepared = self._prepare(
            method,
            path,
            query=query,
            body=body,
            idempotency_key=idempotency_key,
            minimum_timeout=minimum_timeout,
            options=options or {},
        )
        attempt = 0
        while True:
            try:
                status, headers, raw = self._send(prepared, deadline)
            except APIConnectionError as exc:
                check_active(prepared.cancel_event, deadline)
                if attempt >= prepared.max_retries or (
                    isinstance(exc, APITimeoutError) and not retry_on_timeout
                ):
                    raise
                sleep_sync(_backoff(attempt), prepared.cancel_event, deadline)
                attempt += 1
                continue
            data = _body(raw)
            if 200 <= status < 300:
                return _success(status, headers, data)
            error = api_error(status, headers, data)
            if not error.retryable or attempt >= prepared.max_retries:
                raise error
            sleep_sync(_retry_delay(headers, attempt), prepared.cancel_event, deadline)
            attempt += 1


class AsyncTransport(_BaseTransport):
    """AsyncIO transport. Native task cancellation propagates without retrying."""

    def __init__(self, config: ClientConfig, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self._client = client if client is not None else httpx.AsyncClient(timeout=None)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if not self._closed.is_set():
            self._closed.set()
            if self._owns_client:
                await self._client.aclose()

    async def _send(
        self, prepared: _Prepared, deadline: float | None
    ) -> tuple[int, httpx.Headers, bytes]:
        self._check_open()
        check_active(prepared.cancel_event, deadline)
        budget = prepared.timeout
        if deadline is not None:
            budget = min(budget, max(0.0, deadline - time.monotonic()))
        expiry = time.monotonic() + budget

        async def send() -> tuple[int, httpx.Headers, bytes]:
            request = self._request(self._client, prepared, budget)
            response = await self._client.send(
                request, stream=True, auth=None, follow_redirects=False
            )
            try:
                data = await response.aread()
                check_active(prepared.cancel_event, deadline)
                if time.monotonic() >= expiry:
                    raise APITimeoutError("request timed out before its response was delivered")
                return response.status_code, httpx.Headers(response.headers), data
            finally:
                await response.aclose()

        async def cancelled() -> None:
            assert prepared.cancel_event is not None
            while not prepared.cancel_event.is_set():
                await asyncio.sleep(0.01)

        try:
            async with asyncio.timeout(budget):
                if prepared.cancel_event is None:
                    return await send()
                sending = asyncio.create_task(send())
                cancellation = asyncio.create_task(cancelled())
                try:
                    done, _ = await asyncio.wait(
                        (sending, cancellation), return_when=asyncio.FIRST_COMPLETED
                    )
                    if cancellation in done:
                        raise RequestAbortedError("request was aborted")
                    return await sending
                finally:
                    sending.cancel()
                    cancellation.cancel()
                    await asyncio.gather(sending, cancellation, return_exceptions=True)
        except (TimeoutError, httpx.TimeoutException) as exc:
            check_active(prepared.cancel_event, deadline)
            raise APITimeoutError(f"request timed out after {prepared.timeout} seconds") from exc
        except httpx.RequestError as exc:
            raise APIConnectionError("could not connect to the Traceport API") from exc

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str | int] | None = None,
        body: Any = None,
        idempotency_key: str | None = None,
        minimum_timeout: float = 0,
        retry_on_timeout: bool = True,
        options: RequestOptions | None = None,
        deadline: float | None = None,
    ) -> Response:
        prepared = self._prepare(
            method,
            path,
            query=query,
            body=body,
            idempotency_key=idempotency_key,
            minimum_timeout=minimum_timeout,
            options=options or {},
        )
        attempt = 0
        while True:
            try:
                status, headers, raw = await self._send(prepared, deadline)
            except APIConnectionError as exc:
                check_active(prepared.cancel_event, deadline)
                if attempt >= prepared.max_retries or (
                    isinstance(exc, APITimeoutError) and not retry_on_timeout
                ):
                    raise
                await sleep_async(_backoff(attempt), prepared.cancel_event, deadline)
                attempt += 1
                continue
            check_active(prepared.cancel_event, deadline)
            data = _body(raw)
            if 200 <= status < 300:
                return _success(status, headers, data)
            error = api_error(status, headers, data)
            if not error.retryable or attempt >= prepared.max_retries:
                raise error
            await sleep_async(_retry_delay(headers, attempt), prepared.cancel_event, deadline)
            attempt += 1
