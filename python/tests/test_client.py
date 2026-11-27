"""One client serves every product; derived clients keep credentials and connections."""

from __future__ import annotations

import httpx
import pytest

from traceport_ai import AsyncTraceport, InternalServerError, Traceport
from traceport_ai.workflows import AsyncWorkflows, Workflows

from .helpers import RUN_ID, failure, response, run

BASE_URL = "https://api.test/v1"


def recording(seen: list[httpx.Request], *, fail_first: int = 0):
    """A handler that records requests; the first ``fail_first`` answer 503 with Retry-After 0."""

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) <= fail_first:
            return failure(503, headers={"Retry-After": "0"})
        return response(run())

    return handle


def test_products_and_derived_clients_share_one_connection_pool():
    seen: list[httpx.Request] = []
    with httpx.Client(transport=httpx.MockTransport(recording(seen))) as http:
        client = Traceport(api_key="key", base_url=BASE_URL, http_client=http)
        derived = client.with_options(timeout=5)
        for workflows in (Workflows(client), Workflows(client), Workflows(derived)):
            workflows.runs.get(RUN_ID)
    assert len(seen) == 3
    assert all(request.headers["authorization"] == "Bearer key" for request in seen)


def test_with_options_merges_headers_and_leaves_original_unchanged():
    seen: list[httpx.Request] = []
    with httpx.Client(transport=httpx.MockTransport(recording(seen))) as http:
        client = Traceport(
            api_key="key",
            base_url=BASE_URL,
            default_headers={"x-team": "a", "x-keep": "1"},
            http_client=http,
        )
        derived = client.with_options(default_headers={"x-team": "b"})
        Workflows(client).runs.get(RUN_ID)
        Workflows(derived).runs.get(RUN_ID)
    assert seen[0].headers["x-team"] == "a"
    assert seen[1].headers["x-team"] == "b"
    assert seen[1].headers["x-keep"] == "1"
    assert str(seen[1].url) == f"{BASE_URL}/workflow/runs/{RUN_ID}"
    assert derived.base_url == client.base_url


def test_with_options_applies_retries_only_to_the_derived_client():
    seen: list[httpx.Request] = []
    with httpx.Client(transport=httpx.MockTransport(recording(seen, fail_first=2))) as http:
        client = Traceport(api_key="key", base_url=BASE_URL, max_retries=0, http_client=http)
        with pytest.raises(InternalServerError):  # the original makes exactly one attempt
            Workflows(client).runs.get(RUN_ID)
        assert len(seen) == 1
        Workflows(client.with_options(max_retries=1)).runs.get(RUN_ID)
    assert len(seen) == 3


def test_closing_a_derived_client_keeps_the_original_connections_open():
    seen: list[httpx.Request] = []
    client = Traceport(api_key="key", base_url=BASE_URL)
    # Swap in a mock-backed pool owned by the original client.
    client._transport._client.close()
    client._transport._client = httpx.Client(transport=httpx.MockTransport(recording(seen)))
    derived = client.with_options(timeout=5)
    derived.close()
    Workflows(client).runs.get(RUN_ID)
    client.close()
    assert client._transport._client.is_closed
    assert len(seen) == 1


def test_with_options_validates_overrides():
    client = Traceport(api_key="key")
    with pytest.raises((TypeError, ValueError)):
        client.with_options(timeout=0)
    with pytest.raises((TypeError, ValueError)):
        client.with_options(max_retries=-1)


def test_with_options_returns_the_callers_subclass():
    class Extended(Traceport):
        pass

    assert isinstance(Extended(api_key="key").with_options(timeout=1), Extended)


async def test_async_client_with_options_and_product():
    seen: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response(run())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        async with AsyncTraceport(api_key="key", base_url=BASE_URL, http_client=http) as client:
            derived = client.with_options(default_headers={"x-team": "async"})
            await AsyncWorkflows(client).runs.get(RUN_ID)
            await AsyncWorkflows(derived).runs.get(RUN_ID)
    assert len(seen) == 2
    assert seen[1].headers["x-team"] == "async"


def test_products_reject_the_wrong_client_type():
    with pytest.raises(TypeError, match="Async product class"):
        Workflows(AsyncTraceport(api_key="key"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="sync product class"):
        AsyncWorkflows(Traceport(api_key="key"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="expected a traceport_ai.Traceport"):
        Workflows(object())  # type: ignore[arg-type]
