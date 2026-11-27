from __future__ import annotations

import asyncio
import inspect
import json
import threading
from collections import deque
from pathlib import Path

import httpx

from traceport_ai import AsyncTraceport, Traceport
from traceport_ai.workflows import AsyncWorkflows, Workflows

REPO = Path(__file__).resolve().parents[2]
VERSION_ID = "00000000-0000-4000-8000-000000000001"
RUN_ID = "00000000-0000-4000-8000-000000000002"


def run(status="running", **extra):
    return {
        "id": RUN_ID,
        "configVersionID": VERSION_ID,
        "revision": 1,
        "status": status,
        "mode": "production",
        "source": "api_async",
        "createdAt": "2026-11-12T10:00:00Z",
        **extra,
    }


def result(error="", final=None):
    return {
        "data": {"final": {"ok": True} if final is None else final},
        "error": error,
        "steps": [],
    }


def response(data, status=200, headers=None):
    return httpx.Response(
        status, json={"data": data, "error": "", "status": status, "errorCode": ""}, headers=headers
    )


def failure(status=503, message="unavailable", code="test", headers=None):
    return httpx.Response(
        status,
        json={"data": None, "error": message, "status": status, "errorCode": code},
        headers=headers,
    )


class Harness:
    def __init__(self, mode, steps, *, http_options=None, **options):
        self.mode = mode
        self.requests = []
        self.steps = deque(steps)
        self.lock = threading.Lock()
        transport = httpx.MockTransport(self._async if mode == "async" else self._sync)
        http_type = httpx.AsyncClient if mode == "async" else httpx.Client
        client_type = AsyncTraceport if mode == "async" else Traceport
        self.http = http_type(transport=transport, **(http_options or {}))
        settings = {
            "api_key": "test-key",
            "base_url": "https://api.test/v1",
            "max_retries": 0,
            "http_client": self.http,
            **options,
        }
        self.client = client_type(**settings)
        # The workflows product on the shared client, matching the client's mode.
        self.workflows = (AsyncWorkflows if mode == "async" else Workflows)(self.client)

    def _step(self, request):
        with self.lock:
            self.requests.append(request)
            if not self.steps:
                raise AssertionError(f"unexpected request: {request.method} {request.url}")
            return self.steps.popleft()

    def _sync(self, request):
        step = self._step(request)
        if isinstance(step, BaseException):
            raise step
        return step(request) if callable(step) else step

    async def _async(self, request):
        step = self._step(request)
        if isinstance(step, BaseException):
            raise step
        value = step(request) if callable(step) else step
        return await value if inspect.isawaitable(value) else value

    async def call(self, method, *args, **kwargs):
        if self.mode == "async":
            return await method(*args, **kwargs)
        return await asyncio.to_thread(method, *args, **kwargs)

    async def close(self):
        if self.mode == "async":
            await self.client.aclose()
            await self.http.aclose()
        else:
            self.client.close()
            self.http.close()


def fixtures():
    return [json.loads(path.read_text()) for path in sorted((REPO / "fixtures").rglob("*.json"))]
