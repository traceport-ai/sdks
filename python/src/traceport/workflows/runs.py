from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from typing import Any, Unpack
from urllib.parse import quote

from .._core.errors import _ObservationExpired
from .._core.transport import AsyncTransport, Transport, check_active, sleep_async, sleep_sync
from .._core.types import RequestOptions
from .errors import WaitTimeoutError
from .result import parse_page, parse_run
from .types import WorkflowRun, WorkflowRunPage, WorkflowRunStatus
from .validation import idempotency_key as resolve_key
from .validation import list_query, mutation_body, resource_id, wait_settings

_TERMINAL = frozenset({"succeeded", "failed", "interrupted"})


class Runs:
    """Start, read, list and observe durable runs without cancelling server-side work."""

    # Created by Workflows from the shared client's transport; reach it as ``workflows.runs``.
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def start(
        self,
        *,
        version_id: str,
        input: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        **options: Unpack[RequestOptions],
    ) -> WorkflowRun:
        response = self._transport.request(
            "POST",
            "/workflow/runs",
            body=mutation_body(version_id, input),
            idempotency_key=resolve_key(idempotency_key),
            options=options,
        )
        return parse_run(response.data, response.status)

    def _get(
        self, run_id: str, options: RequestOptions, deadline: float | None = None
    ) -> WorkflowRun:
        response = self._transport.request(
            "GET",
            f"/workflow/runs/{quote(resource_id(run_id, 'run_id'), safe='')}",
            options=options,
            deadline=deadline,
        )
        return parse_run(response.data, response.status)

    def get(self, run_id: str, **options: Unpack[RequestOptions]) -> WorkflowRun:
        """Failed and interrupted runs are returned normally."""
        return self._get(run_id, options)

    def list(
        self,
        *,
        version_id: str | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int | None = None,
        offset: int | None = None,
        **options: Unpack[RequestOptions],
    ) -> WorkflowRunPage:
        response = self._transport.request(
            "GET",
            "/workflow/runs",
            query=list_query(version_id, status, limit, offset),
            options=options,
        )
        return parse_page(response.data, response.status)

    def wait_for_completion(
        self,
        run_id: str,
        *,
        timeout: float = 600,
        poll_interval: float = 1,
        max_poll_interval: float = 5,
        request_timeout: float | None = None,
        max_retries: int | None = None,
        headers: Mapping[str, str] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> WorkflowRun:
        """Bound all reads, retries and sleeps by one observation timeout (seconds)."""
        resource_id(run_id, "run_id")
        options = wait_settings(
            timeout, poll_interval, max_poll_interval, request_timeout, max_retries
        )
        if headers is not None:
            options["headers"] = headers
        if cancel_event is not None:
            options["cancel_event"] = cancel_event
        self._transport.validate_options(options)
        deadline = time.monotonic() + timeout
        interval = min(poll_interval, max_poll_interval)
        last: WorkflowRun | None = None
        try:
            while True:
                check_active(cancel_event, deadline)
                run = self._get(run_id, options, deadline)
                check_active(cancel_event, deadline)
                last = run
                if run.status in _TERMINAL:
                    return run
                sleep_sync(interval, cancel_event, deadline)
                interval = min(interval * 1.5, max_poll_interval)
        except _ObservationExpired:
            raise WaitTimeoutError(run_id, last, timeout) from None


class AsyncRuns:
    """AsyncIO durable workflow runs. Native task cancellation propagates unchanged."""

    # Created by AsyncWorkflows; reach it as ``workflows.runs``.
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def start(
        self,
        *,
        version_id: str,
        input: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        **options: Unpack[RequestOptions],
    ) -> WorkflowRun:
        response = await self._transport.request(
            "POST",
            "/workflow/runs",
            body=mutation_body(version_id, input),
            idempotency_key=resolve_key(idempotency_key),
            options=options,
        )
        return parse_run(response.data, response.status)

    async def _get(
        self, run_id: str, options: RequestOptions, deadline: float | None = None
    ) -> WorkflowRun:
        response = await self._transport.request(
            "GET",
            f"/workflow/runs/{quote(resource_id(run_id, 'run_id'), safe='')}",
            options=options,
            deadline=deadline,
        )
        return parse_run(response.data, response.status)

    async def get(self, run_id: str, **options: Unpack[RequestOptions]) -> WorkflowRun:
        return await self._get(run_id, options)

    async def list(
        self,
        *,
        version_id: str | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int | None = None,
        offset: int | None = None,
        **options: Unpack[RequestOptions],
    ) -> WorkflowRunPage:
        response = await self._transport.request(
            "GET",
            "/workflow/runs",
            query=list_query(version_id, status, limit, offset),
            options=options,
        )
        return parse_page(response.data, response.status)

    async def wait_for_completion(
        self,
        run_id: str,
        *,
        timeout: float = 600,
        poll_interval: float = 1,
        max_poll_interval: float = 5,
        request_timeout: float | None = None,
        max_retries: int | None = None,
        headers: Mapping[str, str] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> WorkflowRun:
        resource_id(run_id, "run_id")
        options = wait_settings(
            timeout, poll_interval, max_poll_interval, request_timeout, max_retries
        )
        if headers is not None:
            options["headers"] = headers
        if cancel_event is not None:
            options["cancel_event"] = cancel_event
        self._transport.validate_options(options)
        deadline = time.monotonic() + timeout
        interval = min(poll_interval, max_poll_interval)
        last: WorkflowRun | None = None
        try:
            while True:
                check_active(cancel_event, deadline)
                run = await self._get(run_id, options, deadline)
                check_active(cancel_event, deadline)
                last = run
                if run.status in _TERMINAL:
                    return run
                await sleep_async(interval, cancel_event, deadline)
                interval = min(interval * 1.5, max_poll_interval)
        except _ObservationExpired:
            raise WaitTimeoutError(run_id, last, timeout) from None
