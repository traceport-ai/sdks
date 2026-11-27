# Changelog

## 0.0.1 (Unreleased)

Initial release of `traceport-ai` (import `traceport_ai`): the shared clients in `traceport_ai` and the workflows product in
`traceport_ai.workflows`. This version has not been published.

### Clients and configuration

- Python 3.11+ synchronous `Traceport` and AsyncIO `AsyncTraceport` clients, with HTTPX and Pydantic 2 as the only direct runtime dependencies.
- API key and `/v1` base URL configuration through arguments or `TRACEPORT_API_KEY` / `TRACEPORT_BASE_URL`.
- Injectable HTTPX clients, default/per-request headers, request timeouts in seconds and retry limits.
- Sync/async context managers and explicit close methods for owned connections; injected clients remain caller-owned.
- One shared client per mode passed to product classes; `with_options` derives a client with the same credentials, base URL and connection pool but different timeouts, retries or default headers.

### Workflows and results

- `Workflows(client)` and `AsyncWorkflows(async_client)` product classes; `execute` for synchronous workflow execution.
- `deployment=` runs whichever version is deployed to a stable code; `version_id=` pins one version. Exactly one is required (`TypeError` before sending otherwise). `WorkflowRun.deployment` and the `deployment=` list filter expose and filter by the code.
- `runs.start`, `get` and `list` for durable runs, including version/status filters and offset pagination.
- `runs.wait_for_completion` with configurable observation timeout, request timeout and polling intervals.
- Typed Pydantic run, step, page and billing-receipt models with snake_case properties, API wire aliases, parsed timestamps, decimal-string billing amounts and preserved extra fields.
- Workflow failures returned as normal results, retaining partial output, raw data and executed steps.
- Interpreted stored results, final-output selection with a full-data fallback, and `traceport_ai.workflows.require_output` and model `require_output` helpers with optional schema decoding.

### Reliability and errors

- Generated or caller-supplied idempotency keys and stable serialized request bodies across retries.
- Automatic retries for connection/body I/O failures and HTTP 408, 429, 500, 502, 503 and 504, with jittered backoff and capped `Retry-After` support.
- Full-attempt timeouts through response-body reads, plus observation deadlines covering reads, retries and poll delays.
- Separate synchronous-execution timeout behavior: a timed-out `execute` is not retried in either client.
- Optional cancellation events and native AsyncIO task cancellation without retries, with response-stream cleanup.
- Protected Authorization/Idempotency-Key headers and validation of numeric settings and required resource fields.
- Typed HTTP, connection, timeout, cancellation, response, workflow-failure and wait-timeout exceptions, preserving response metadata and chained network causes.
- Optional request IDs, in-progress replay run IDs, and the last observed run on wait timeout when available.

### Distribution and examples

- Wheel and source distribution with `py.typed`, license metadata and an isolated installed-wheel verification command.
- Sync execution, async execution, durable-run and opt-in live-conformance examples; shared fixture/contract tests for both clients and locked development dependencies.

Live API verification, registry ownership and publication remain pending.
