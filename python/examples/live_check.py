"""Opt-in sandbox C-01–C-08. Run normally or with --async-client. Consumes real usage."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import os
import uuid
from collections.abc import Callable
from typing import Any

from traceport import AsyncTraceport, AuthenticationError, ConflictError, Traceport
from traceport.workflows import AsyncWorkflows, WaitTimeoutError, Workflows, require_output


def product(client: Traceport | AsyncTraceport) -> Workflows | AsyncWorkflows:
    """The workflows product for either client mode, on the same client."""
    return AsyncWorkflows(client) if isinstance(client, AsyncTraceport) else Workflows(client)


async def call(method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    if inspect.iscoroutinefunction(method):
        return await method(*args, **kwargs)
    return await asyncio.to_thread(method, *args, **kwargs)


async def check(use_async: bool) -> None:
    version_ok = os.environ["TRACEPORT_CONFORMANCE_VERSION_OK"]
    version_fail = os.environ["TRACEPORT_CONFORMANCE_VERSION_FAIL"]
    client: Traceport | AsyncTraceport = AsyncTraceport() if use_async else Traceport()
    workflows = product(client)
    try:
        params = {"version_id": version_ok, "input": {"question": "SDK live check"}}
        result = await call(workflows.execute, **params)
        assert result.status == "succeeded", result.error
        print("PASS C-01 execute success", require_output(result))

        failed = await call(workflows.execute, version_id=version_fail, input=params["input"])
        assert failed.status == "failed" and failed.error
        print("PASS C-02 failed workflow is a normal outcome")

        bad: Traceport | AsyncTraceport = (
            AsyncTraceport(api_key="invalid-test-key", base_url=client.base_url, max_retries=0)
            if use_async
            else Traceport(api_key="invalid-test-key", base_url=client.base_url, max_retries=0)
        )
        try:
            try:
                await call(product(bad).execute, **params)
            except AuthenticationError:
                print("PASS C-03 authentication error")
            else:
                raise AssertionError("C-03 expected AuthenticationError")
        finally:
            if isinstance(bad, AsyncTraceport):
                await bad.aclose()
            else:
                bad.close()

        key = str(uuid.uuid4())
        run = await call(workflows.runs.start, **params, idempotency_key=key)
        finished = await call(workflows.runs.wait_for_completion, run.id, timeout=120)
        assert finished.id == run.id and finished.status == "succeeded"
        require_output(finished)
        print("PASS C-04 durable start and completion")

        replay = await call(workflows.runs.start, **params, idempotency_key=key)
        assert replay.id == run.id
        print("PASS C-05 same-key replay")
        try:
            await call(
                workflows.runs.start,
                version_id=version_ok,
                input={"question": "different"},
                idempotency_key=key,
            )
        except ConflictError:
            print("PASS C-06 changed input conflicts")
        else:
            raise AssertionError("C-06 expected ConflictError")

        observed = await call(workflows.runs.start, **params)
        try:
            await call(workflows.runs.wait_for_completion, observed.id, timeout=0.001)
        except WaitTimeoutError:
            await call(workflows.runs.wait_for_completion, observed.id, timeout=120)
            print("PASS C-07 timeout leaves the run alive")
        else:
            print("SKIP C-07 run already terminal; use a slower workflow")

        page = await call(
            workflows.runs.list, version_id=version_ok, status="succeeded", limit=2, offset=0
        )
        assert 0 < len(page.items) <= 2 and page.limit == 2 and page.offset == 0
        for index, item in enumerate(page.items):
            assert item.config_version_id == version_ok and item.status == "succeeded"
            assert item.output is None and item.result is None
            if index:
                assert item.created_at <= page.items[index - 1].created_at
        print("PASS C-08 filtered summaries")

        first = await call(workflows.execute, **params, idempotency_key=key + "-sync")
        second = await call(workflows.execute, **params, idempotency_key=key + "-sync")
        assert first.output == second.output
        print("PASS synchronous replay")
    finally:
        if isinstance(client, AsyncTraceport):
            await client.aclose()
        else:
            client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--async-client", action="store_true")
    asyncio.run(check(parser.parse_args().async_client))
