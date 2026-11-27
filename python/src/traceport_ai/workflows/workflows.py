from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Unpack

from .._client import AsyncTraceport, Traceport, async_transport_of, transport_of
from .._core.types import RequestOptions
from .result import parse_result
from .runs import AsyncRuns, Runs
from .types import WorkflowResult
from .validation import idempotency_key as resolve_key
from .validation import mutation_body


class Workflows:
    """Synchronous workflow execution and durable runs.

    Takes the shared :class:`traceport_ai.Traceport` client; its credentials, base URL, timeouts and
    retries apply to every call. Use ``client.with_options(...)`` to give workflows different
    settings without a second client.
    """

    def __init__(self, client: Traceport) -> None:
        self._transport = transport_of(client)
        self.runs = Runs(self._transport)

    def execute(
        self,
        *,
        deployment: str | None = None,
        version_id: str | None = None,
        input: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        **options: Unpack[RequestOptions],
    ) -> WorkflowResult:
        """Return a workflow outcome. A timed-out execute is never retried.

        Pass exactly one of ``deployment`` (a stable code; recommended) or
        ``version_id`` (pins one live version).
        """
        response = self._transport.request(
            "POST",
            "/workflow/execute",
            body=mutation_body(version_id, deployment, input),
            idempotency_key=resolve_key(idempotency_key),
            minimum_timeout=360,
            retry_on_timeout=False,
            options=options,
        )
        return parse_result(response.data, response.status)


class AsyncWorkflows:
    """AsyncIO workflow execution and durable runs, on a shared
    :class:`traceport_ai.AsyncTraceport` client."""

    def __init__(self, client: AsyncTraceport) -> None:
        self._transport = async_transport_of(client)
        self.runs = AsyncRuns(self._transport)

    async def execute(
        self,
        *,
        deployment: str | None = None,
        version_id: str | None = None,
        input: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        **options: Unpack[RequestOptions],
    ) -> WorkflowResult:
        response = await self._transport.request(
            "POST",
            "/workflow/execute",
            body=mutation_body(version_id, deployment, input),
            idempotency_key=resolve_key(idempotency_key),
            minimum_timeout=360,
            retry_on_timeout=False,
            options=options,
        )
        return parse_result(response.data, response.status)
