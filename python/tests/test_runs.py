import asyncio
import math
import threading
import time

import pytest

from traceport import APITimeoutError, InvalidResponseError
from traceport.workflows import (
    WaitTimeoutError,
    WorkflowFailedError,
    WorkflowResult,
    WorkflowRun,
    require_output,
)

from .helpers import RUN_ID, VERSION_ID, failure, response, run
from .test_transport import slow_response


@pytest.mark.parametrize("terminal", ["succeeded", "failed", "interrupted"])
async def test_polling_to_terminal_status(make, terminal):
    h = make([response(run("queued")), response(run("running")), response(run(terminal))])
    value = await h.call(
        h.workflows.runs.wait_for_completion,
        RUN_ID,
        poll_interval=0.001,
        max_poll_interval=0.002,
    )
    assert value.status == terminal
    assert len(h.requests) == 3


async def test_observation_timeout_before_first_status(make, mode):
    reply, closed = slow_response(mode, delay=0.15)
    h = make([reply], max_retries=2)
    start = time.monotonic()
    with pytest.raises(WaitTimeoutError) as error:
        await h.call(h.workflows.runs.wait_for_completion, RUN_ID, timeout=0.03)
    assert error.value.last_run is None
    assert error.value.run_id == RUN_ID
    assert time.monotonic() - start < 0.12
    assert len(h.requests) == 1
    assert await asyncio.to_thread(closed.wait, 0.5)


@pytest.mark.parametrize("phase", ["sleep", "backoff", "read"])
async def test_observation_bounds_all_waiting_and_retains_last_run(make, mode, phase):
    replies = [response(run())]
    closed = None
    if phase == "backoff":
        replies.append(failure(headers={"Retry-After": "60"}))
    elif phase == "read":
        reply, closed = slow_response(mode, delay=0.15)
        replies.append(reply)
    h = make(replies, max_retries=2)
    with pytest.raises(WaitTimeoutError) as error:
        await h.call(
            h.workflows.runs.wait_for_completion,
            RUN_ID,
            timeout=0.04,
            poll_interval=1 if phase == "sleep" else 0.001,
        )
    assert error.value.last_run.status == "running"
    assert len(h.requests) == (1 if phase == "sleep" else 2)
    if closed is not None:
        assert await asyncio.to_thread(closed.wait, 0.5)


async def test_shorter_request_timeout_remains_distinct(make, mode):
    reply, closed = slow_response(mode)
    h = make([reply])
    with pytest.raises(APITimeoutError):
        await h.call(h.workflows.runs.wait_for_completion, RUN_ID, timeout=1, request_timeout=0.02)
    assert await asyncio.to_thread(closed.wait, 0.5)


@pytest.mark.parametrize(
    "name", ["timeout", "poll_interval", "max_poll_interval", "request_timeout"]
)
@pytest.mark.parametrize("value", [0, -1, math.inf, math.nan, True])
async def test_wait_options_are_validated_before_http(make, name, value):
    h = make([])
    with pytest.raises(TypeError):
        await h.call(h.workflows.runs.wait_for_completion, RUN_ID, **{name: value})
    assert h.requests == []


@pytest.mark.parametrize("key", ["", "bad key", "x" * 201, "tab\there", "newline\n"])
async def test_invalid_idempotency_key(make, key):
    h = make([])
    with pytest.raises(TypeError):
        await h.call(h.workflows.runs.start, version_id=VERSION_ID, idempotency_key=key)
    assert h.requests == []


@pytest.mark.parametrize(
    "field", ["id", "configVersionID", "revision", "status", "mode", "source", "createdAt"]
)
@pytest.mark.parametrize("operation", ["start", "get", "list"])
async def test_required_resource_fields(make, field, operation):
    data = run()
    data.pop(field)
    payload = {"items": [data], "limit": 50, "offset": 0} if operation == "list" else data
    status = 202 if operation == "start" else 200
    h = make([response(payload, status)])
    with pytest.raises(InvalidResponseError) as error:
        if operation == "start":
            await h.call(h.workflows.runs.start, version_id=VERSION_ID)
        elif operation == "get":
            await h.call(h.workflows.runs.get, RUN_ID)
        else:
            await h.call(h.workflows.runs.list)
    assert error.value.status == status


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", "1"),
        ("revision", True),
        ("revision", -1),
        ("status", "unknown"),
        ("mode", "unknown"),
        ("createdAt", 123),
        ("id", " "),
    ],
)
async def test_wrong_resource_types(make, field, value):
    h = make([response({**run(), field: value})])
    with pytest.raises(InvalidResponseError):
        await h.call(h.workflows.runs.get, RUN_ID)


async def test_raw_fields_and_unknown_output(make):
    data = run("succeeded", output={"futureOutputShape": True}, extraServerField=42)
    h = make([response(data)])
    value = await h.call(h.workflows.runs.get, RUN_ID)
    assert value.result is None
    assert value.output == {"futureOutputShape": True}
    assert value.model_extra["extraServerField"] == 42
    assert value.model_dump(by_alias=True)["configVersionID"] == VERSION_ID


def test_require_output_partial_results_and_decoding():
    success = WorkflowResult(status="succeeded", output={"a": 1}, data={}, steps=[])
    assert require_output(success, lambda output: output["a"]) == 1
    assert success.require_output() == {"a": 1}
    failed = WorkflowResult(status="failed", output={"partial": True}, error="boom", data={})
    with pytest.raises(WorkflowFailedError) as error:
        require_output(failed)
    assert error.value.result is failed
    assert error.value.result.output == {"partial": True}
    resource = WorkflowRun.model_validate(run("succeeded"))
    resource.result = success
    assert resource.require_output() == {"a": 1}
    resource.result = None
    with pytest.raises(WorkflowFailedError, match="no output"):
        resource.require_output()


async def test_no_extra_poll_at_deadline(make):
    h = make([response(run()), response(run("succeeded"))])
    with pytest.raises(WaitTimeoutError):
        await h.call(h.workflows.runs.wait_for_completion, RUN_ID, timeout=0.02, poll_interval=1)
    assert len(h.requests) == 1


async def test_first_poll_interval_is_capped(make):
    h = make([response(run()), response(run("succeeded"))])
    value = await h.call(
        h.workflows.runs.wait_for_completion,
        RUN_ID,
        timeout=0.5,
        poll_interval=1,
        max_poll_interval=0.001,
    )
    assert value.status == "succeeded"


async def test_cancel_while_polling(make):
    from traceport import RequestAbortedError

    cancel = threading.Event()
    h = make([response(run())])
    pending = asyncio.create_task(
        h.call(
            h.workflows.runs.wait_for_completion,
            RUN_ID,
            cancel_event=cancel,
            poll_interval=1,
        )
    )
    await asyncio.sleep(0.02)
    cancel.set()
    with pytest.raises(RequestAbortedError):
        await pending
    assert len(h.requests) == 1
