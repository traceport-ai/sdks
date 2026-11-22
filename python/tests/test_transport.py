import asyncio
import json
import math
import threading
import time
import uuid

import httpx
import pytest

from traceport import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncTraceport,
    InvalidResponseError,
    RequestAbortedError,
    Traceport,
    TraceportError,
)
from traceport.workflows import AsyncWorkflows, Workflows

from .helpers import RUN_ID, VERSION_ID, failure, response, result, run


@pytest.mark.parametrize(
    "setting",
    [
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": math.nan},
        {"timeout": math.inf},
        {"timeout": True},
        {"max_retries": -1},
        {"max_retries": 1.5},
        {"max_retries": math.inf},
        {"max_retries": True},
        {"base_url": "/v1"},
        {"base_url": "ftp://api.test/v1"},
        {"base_url": "https://user:pass@api.test/v1"},
        {"base_url": "https://api.test/v1?x=1"},
        {"base_url": "https://api.test/v1#frag"},
    ],
)
def test_invalid_client_configuration(mode, setting):
    client_type = AsyncTraceport if mode == "async" else Traceport
    with pytest.raises(TypeError):
        client_type(api_key="key", **setting)


@pytest.mark.parametrize(
    "setting",
    [
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": math.nan},
        {"timeout": math.inf},
        {"timeout": True},
        {"max_retries": -1},
        {"max_retries": 1.5},
        {"max_retries": math.inf},
        {"max_retries": True},
        {"headers": {"x": 1}},
        {"cancel_event": True},
    ],
)
async def test_invalid_request_options_never_send(make, setting):
    h = make([])
    with pytest.raises(TypeError):
        await h.call(h.workflows.runs.get, RUN_ID, **setting)
    assert h.requests == []


async def test_environment_defaults(mode, monkeypatch):
    monkeypatch.setenv("TRACEPORT_API_KEY", " env-key ")
    monkeypatch.setenv("TRACEPORT_BASE_URL", "https://env.test/v1/")
    seen = []

    def handler(request):
        seen.append(request)
        return response(run())

    if mode == "sync":
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            with Traceport(http_client=http) as sdk:
                await asyncio.to_thread(Workflows(sdk).runs.get, RUN_ID)
                assert sdk.base_url == "https://env.test/v1"
            assert not http.is_closed
    else:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            async with AsyncTraceport(http_client=http) as sdk:
                await AsyncWorkflows(sdk).runs.get(RUN_ID)
                assert sdk.base_url == "https://env.test/v1"
            assert not http.is_closed
    assert seen[0].headers["authorization"] == "Bearer env-key"
    assert str(seen[0].url) == f"https://env.test/v1/workflow/runs/{RUN_ID}"
    monkeypatch.delenv("TRACEPORT_API_KEY")
    with pytest.raises(TraceportError, match="missing API key"):
        (AsyncTraceport if mode == "async" else Traceport)()


@pytest.mark.parametrize("operation", ["execute", "start"])
async def test_protected_credentials_and_idempotency(make, operation):
    replies = [response(result() if operation == "execute" else run("queued")) for _ in range(3)]
    h = make(
        replies,
        default_headers={
            "Authorization": "default-other",
            "Idempotency-Key": "shared",
            "x-team": "default",
        },
        http_options={
            "headers": {"Authorization": "borrowed", "Idempotency-Key": "borrowed"},
            "auth": ("wrong", "wrong"),
        },
    )
    method = h.workflows.execute if operation == "execute" else h.workflows.runs.start
    for key in ("job-one", "job-two", None):
        options = {"idempotency_key": key} if key else {}
        await h.call(
            method,
            version_id=VERSION_ID,
            headers={"AUTHORIZATION": "request-other", "IDEMPOTENCY-KEY": "", "x-team": "request"},
            **options,
        )
    assert [r.headers["idempotency-key"] for r in h.requests[:2]] == ["job-one", "job-two"]
    assert uuid.UUID(h.requests[2].headers["idempotency-key"]).version == 4
    for request in h.requests:
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.headers["x-team"] == "request"
        assert request.headers["user-agent"].startswith("traceport-python/")
        assert json.loads(request.content) == {"configVersionID": VERSION_ID, "additional": {}}


async def test_reads_do_not_inherit_idempotency_keys(make):
    h = make(
        [response(run())],
        default_headers={"Idempotency-Key": "default"},
        http_options={"headers": {"Idempotency-Key": "borrowed"}},
    )
    await h.call(h.workflows.runs.get, RUN_ID, headers={"idempotency-key": "request"})
    assert "idempotency-key" not in h.requests[0].headers
    assert "content-type" not in h.requests[0].headers


@pytest.mark.parametrize("key", ["job-café", "job-😀"])
async def test_utf8_idempotency_keys(make, key):
    h = make([response(run("queued"))])
    await h.call(h.workflows.runs.start, version_id=VERSION_ID, idempotency_key=key)
    assert h.requests[0].headers["Idempotency-Key"] == key


async def test_retry_preserves_exact_body_and_key(make):
    h = make([failure(headers={"Retry-After": "0"}), response(run("queued"), 202)], max_retries=2)
    value = await h.call(h.workflows.runs.start, version_id=VERSION_ID, input={"a": 1})
    assert value.id == RUN_ID
    assert len(h.requests) == 2
    assert h.requests[0].content == h.requests[1].content
    assert h.requests[0].headers["idempotency-key"] == h.requests[1].headers["idempotency-key"]


async def test_retry_limit_and_per_call_override(make):
    h = make([failure(headers={"Retry-After": "0"}) for _ in range(3)], max_retries=2)
    with pytest.raises(APIError) as error:
        await h.call(h.workflows.runs.get, RUN_ID)
    assert error.value.status == 503
    assert len(h.requests) == 3
    h2 = make([failure()], max_retries=2)
    with pytest.raises(APIError):
        await h2.call(h2.workflows.runs.get, RUN_ID, max_retries=0)
    assert len(h2.requests) == 1


async def test_retry_after_delay(make):
    h = make([failure(headers={"Retry-After": "0.03"}), response(run())], max_retries=1)
    start = time.monotonic()
    await h.call(h.workflows.runs.get, RUN_ID)
    assert time.monotonic() - start >= 0.025
    assert len(h.requests) == 2


class SlowSync(httpx.SyncByteStream):
    def __init__(self, delay, closed, payload=b"{}"):
        self.delay, self.closed, self.payload = delay, closed, payload

    def __iter__(self):
        time.sleep(self.delay)
        yield self.payload

    def close(self):
        self.closed.set()


class SlowAsync(httpx.AsyncByteStream):
    def __init__(self, delay, closed, payload=b"{}"):
        self.delay, self.closed, self.payload = delay, closed, payload

    async def __aiter__(self):
        await asyncio.sleep(self.delay)
        yield self.payload

    async def aclose(self):
        self.closed.set()


def slow_response(mode, delay=0.08, status=200):
    closed = threading.Event()
    stream = (SlowAsync if mode == "async" else SlowSync)(delay, closed)
    return httpx.Response(status, stream=stream), closed


@pytest.mark.parametrize("status", [200, 503])
async def test_full_body_timeout(make, mode, status):
    reply, closed = slow_response(mode, status=status)
    h = make([reply])
    started = time.monotonic()
    with pytest.raises(APITimeoutError):
        await h.call(h.workflows.runs.get, RUN_ID, timeout=0.02)
    assert time.monotonic() - started < 0.07
    assert await asyncio.to_thread(closed.wait, 0.5)
    assert len(h.requests) == 1


@pytest.mark.parametrize("operation", ["get", "start", "execute"])
async def test_body_timeout_retry_policy(make, mode, operation):
    reply, closed = slow_response(mode)
    h = make([reply, response(run("succeeded"))], max_retries=1)
    method = {
        "get": h.workflows.runs.get,
        "start": h.workflows.runs.start,
        "execute": h.workflows.execute,
    }[operation]
    if operation == "execute":
        with pytest.raises(APITimeoutError):
            await h.call(method, version_id=VERSION_ID, timeout=0.02)
        assert len(h.requests) == 1
    else:
        args = (RUN_ID,) if operation == "get" else ()
        kwargs = {} if operation == "get" else {"version_id": VERSION_ID}
        value = await h.call(method, *args, timeout=0.02, **kwargs)
        assert value.id == RUN_ID
        assert len(h.requests) == 2
    assert await asyncio.to_thread(closed.wait, 0.5)


async def test_execute_default_and_override_timeout(make):
    h = make([response(result()), response(result())], timeout=1)
    await h.call(h.workflows.execute, version_id=VERSION_ID)
    await h.call(h.workflows.execute, version_id=VERSION_ID, timeout=1)
    assert h.requests[0].extensions["timeout"]["read"] >= 359
    assert 0 < h.requests[1].extensions["timeout"]["read"] <= 1


async def test_cancel_event_before_and_during_body(make, mode):
    cancel = threading.Event()
    cancel.set()
    h = make([])
    with pytest.raises(RequestAbortedError):
        await h.call(h.workflows.runs.get, RUN_ID, cancel_event=cancel)
    assert h.requests == []
    cancel.clear()
    reply, closed = slow_response(mode, delay=0.15)
    h2 = make([reply], max_retries=2)
    pending = asyncio.create_task(h2.call(h2.workflows.runs.get, RUN_ID, cancel_event=cancel))
    await asyncio.sleep(0.02)
    cancel.set()
    with pytest.raises(RequestAbortedError):
        await pending
    assert len(h2.requests) == 1
    assert await asyncio.to_thread(closed.wait, 0.5)


async def test_async_task_cancellation_is_not_retried():
    closed = threading.Event()
    reply = httpx.Response(200, stream=SlowAsync(10, closed))
    calls = []

    async def handler(request):
        calls.append(request)
        return reply

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with AsyncTraceport(api_key="test", http_client=http) as sdk:
            pending = asyncio.create_task(AsyncWorkflows(sdk).runs.get(RUN_ID))
            await asyncio.sleep(0.01)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
    assert closed.is_set()
    assert len(calls) == 1


async def test_async_rejects_a_late_response_even_if_transport_suppresses_cancellation():
    async def handler(request):
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        return response(run("succeeded"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with AsyncTraceport(api_key="key", max_retries=0, http_client=http) as sdk:
            with pytest.raises(APITimeoutError):
                await AsyncWorkflows(sdk).runs.get(RUN_ID, timeout=0.01)


class BrokenSync(httpx.SyncByteStream):
    def __iter__(self):
        raise httpx.ReadError("socket reset")
        yield b""  # Make this a generator.


class BrokenAsync(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise httpx.ReadError("socket reset")
        yield b""


@pytest.mark.parametrize("phase", ["connect", "body"])
async def test_connection_errors_and_recovery(make, mode, phase):
    step = (
        httpx.ConnectError("connect failed")
        if phase == "connect"
        else httpx.Response(200, stream=(BrokenAsync if mode == "async" else BrokenSync)())
    )
    h = make([step, response(run())], max_retries=1)
    assert (await h.call(h.workflows.runs.get, RUN_ID)).id == RUN_ID
    assert len(h.requests) == 2
    h2 = make([httpx.ReadError("unrecoverable")])
    with pytest.raises(APIConnectionError) as caught:
        await h2.call(h2.workflows.runs.get, RUN_ID)
    assert isinstance(caught.value.__cause__, httpx.ReadError)


@pytest.mark.parametrize(
    "status,retryable",
    [
        (400, False),
        (401, False),
        (402, False),
        (403, False),
        (404, False),
        (408, True),
        (409, False),
        (422, False),
        (429, True),
        (500, True),
        (501, False),
        (502, True),
        (503, True),
        (504, True),
    ],
)
async def test_error_metadata(make, status, retryable):
    h = make([failure(status, code="specific_code", headers={"X-Request-Id": "req_1"})])
    with pytest.raises(APIError) as error:
        await h.call(h.workflows.runs.get, RUN_ID)
    assert error.value.status == status
    assert error.value.error_code == "specific_code"
    assert error.value.retryable is retryable
    assert error.value.request_id == "req_1"


@pytest.mark.parametrize("body", ["not json", {}, {"data": None, "error": "boom"}, {"data": 123}])
async def test_malformed_success_is_not_retried(make, body):
    reply = (
        httpx.Response(200, text=body) if isinstance(body, str) else httpx.Response(200, json=body)
    )
    h = make([reply], max_retries=2)
    with pytest.raises(InvalidResponseError):
        await h.call(h.workflows.runs.get, RUN_ID)
    assert len(h.requests) == 1


async def test_closed_client_and_borrowed_http_client(make):
    h = make([])
    if h.mode == "sync":
        h.client.close()
    else:
        await h.client.aclose()
    assert not h.http.is_closed
    with pytest.raises(TraceportError, match="closed"):
        await h.call(h.workflows.runs.get, RUN_ID)
    assert h.requests == []
