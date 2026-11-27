# Traceport Python SDK

Python 3.11+ Traceport SDK with synchronous `Traceport` and AsyncIO `AsyncTraceport`
clients. The only direct runtime dependencies are HTTPX and Pydantic 2.

**0.0.1 pre-release, unpublished.** The distribution name is `traceport-ai` and the import name is `traceport_ai` (the PyPI
name `traceport_ai` belongs to an unrelated project); registry
ownership, live-server conformance and publication remain release gates.

The SDK is modular: one shared client and a subpackage per product. Every product takes
the same client, so the API key, base URL, timeouts and retries are configured once.

| Module | Contents |
| --- | --- |
| `traceport_ai` | `Traceport` / `AsyncTraceport` clients, request options and request errors. |
| `traceport_ai.workflows` | `Workflows` / `AsyncWorkflows`: execute saved workflows and manage durable runs. |

Document parsing will ship as `traceport_ai.documents`, taking the same client. Products that
need extra dependencies will install them through an extra, for example
`traceport-ai[documents]`; workflows needs none.

Use a Traceport API key and an active, published workflow version. This release
supports workflow execution and durable runs; document parsing, Human input, events
and workflow cancellation are not included. See the [changelog](https://github.com/traceport-ai/sdks/blob/main/python/CHANGELOG.md)
for the complete first-release feature set.

## Install locally

From `sdks/python/`, using Python 3.11 or later:

```sh
python -m pip install .
```

You can also install a locally built wheel with
`python -m pip install /absolute/path/to/sdks/python/dist/traceport_ai-0.0.1-py3-none-any.whl`.
After publication, installation will be `python -m pip install traceport-ai`.

For development, use the checked-in dependency lock:

```sh
python -m pip install uv==0.13.8
uv sync --locked --all-extras
```

## Synchronous execution

```python
from traceport_ai import Traceport
from traceport_ai.workflows import Workflows

with Traceport() as client:  # TRACEPORT_API_KEY; optional TRACEPORT_BASE_URL
    workflows = Workflows(client)  # other products take the same client
    result = workflows.execute(
        deployment="support-triage-prod",  # or version_id="<workflow-version-id>"
        input={"question": "What is Traceport?"},
    )
    if result.status == "succeeded":
        print(result.output)
    else:
        print(result.error, result.output)  # partial output
```

A workflow that ran and failed is a normal result, including HTTP-200 failures.
Request/authentication/network problems raise typed exceptions.

## Asynchronous execution

```python
import asyncio
from traceport_ai import AsyncTraceport
from traceport_ai.workflows import AsyncWorkflows


async def main() -> None:
    async with AsyncTraceport() as client:
        result = await AsyncWorkflows(client).execute(
            deployment="support-triage-prod",
            input={"question": "Hello"},
        )
        print(result.status, result.output, result.error)


asyncio.run(main())
```

AsyncTraceport uses AsyncIO. Native task cancellation propagates as
`asyncio.CancelledError` and is never retried.

### Supported methods

`Workflows` (with `Traceport`) and `AsyncWorkflows` (with `AsyncTraceport`) expose the same
methods; await each call on `AsyncWorkflows`. Passing the wrong client type raises TypeError.

| Method                               | Purpose                                             |
| ------------------------------------ | --------------------------------------------------- |
| `workflows.execute`                  | Run a published version and wait for its outcome.   |
| `workflows.runs.start`               | Start a durable background run and return its ID.   |
| `workflows.runs.get`                 | Read a run, including stored output when available. |
| `workflows.runs.list`                | Read a page of run summaries.                       |
| `workflows.runs.wait_for_completion` | Poll an existing run to a terminal status.          |

## Configuration

```python
import httpx
from traceport_ai import Traceport
from traceport_ai.workflows import Workflows

with httpx.Client() as http:
    with Traceport(
        api_key="<key>",
        base_url="https://api.traceport.ai/v1",
        timeout=60,  # seconds per attempt
        max_retries=2,  # zero disables retries
        default_headers={"x-team": "search"},
        http_client=http,  # optional; remains owned by its caller
    ) as client:
        run = Workflows(client).runs.get(
            "<run-id>",
            timeout=10,
            max_retries=0,
            headers={"traceparent": "<trace-context>"},
        )
```

- Defaults: `TRACEPORT_API_KEY`; `TRACEPORT_BASE_URL` then
  `https://api.traceport.ai/v1`; 60 seconds and two retries.
- All timeouts and polling intervals use **seconds**, must be finite and positive;
  retry counts must be non-negative integers. Booleans are not valid numeric settings.
  Invalid local settings raise TypeError before HTTP is sent.
- Execute defaults to at least 360 seconds to accommodate the server's execution
  budget. A per-call `timeout` overrides that minimum.
- Request timeouts apply per attempt; retries and backoff can extend the logical
  call. The `timeout` on `wait_for_completion` instead bounds the whole observation;
  `request_timeout` controls each polling read.
- Per-call `timeout`, `max_retries`, `headers` and an optional `threading.Event`
  named `cancel_event` are supported. A set cancellation event raises
  RequestAbortedError without retrying. Set the event from another thread to stop
  a synchronous call; in AsyncIO, native task cancellation is also available.
  KeyboardInterrupt propagates normally.
- Timeouts cover the complete attempt, including response-body reads. SDK request
  timeout settings override HTTPX client's default network-phase timeouts.
- Synchronous I/O runs in a daemon worker so the caller's absolute budget is bounded.
  Custom HTTP transports must honor HTTPX timeouts; cleanup of an abandoned blocking
  read finishes when that I/O returns. AsyncIO cancellation closes response streams.
- Use context managers, `close()` or `await aclose()` to release owned connections.
  An injected HTTP client remains open and must be closed by its caller. A closed
  SDK client rejects further requests.
- Use `httpx.Client` for Traceport and `httpx.AsyncClient` for AsyncTraceport.
  Extra headers and injected client defaults cannot replace Authorization or the
  resolved Idempotency-Key. Redirects are not automatically followed.

### Derived clients

`client.with_options(timeout=..., max_retries=..., default_headers=...)` returns a client
with the same API key, base URL and connection pool, and different settings. Use it to
give one product different timeouts or retries without a second client. Default headers
are merged over the original's; the original is unchanged.

```python
patient = client.with_options(timeout=300, max_retries=5)
workflows = Workflows(patient)
```

The derived client borrows the original's connections and does not own them: closing it
leaves the original open, and it stops working once the original is closed.

## Deployment codes or version IDs

Pass exactly one of:

- `deployment` (recommended): a stable code such as `"support-triage-prod"`, created on the
  workflow's Deployments tab in the dashboard. The server runs whichever version is deployed
  to it, so shipping a new version needs no change in your code. An unknown code raises
  `NotFoundError` (`deployment_not_found`); a code with nothing deployed raises
  `ConflictError` (`deployment_empty`).
- `version_id`: pins one exact version. It must be live (deployed to at least one code).

Passing both or neither raises `TypeError` before any request is sent. Runs started by
code carry it in `run.deployment`.

## Durable runs

```python
from traceport_ai import Traceport
from traceport_ai.workflows import WaitTimeoutError, Workflows, require_output

deployment = "support-triage-prod"
job_id = "<persisted-logical-job-id>"

with Traceport() as client:
    workflows = Workflows(client)
    run = workflows.runs.start(
        deployment=deployment,
        input={"question": "Hello"},
        idempotency_key=job_id,  # persist one key per logical operation
    )
    # Persist run.id; another process can read it later.
    try:
        finished = workflows.runs.wait_for_completion(
            run.id,
            timeout=120,
            request_timeout=10,
            poll_interval=1,
            max_poll_interval=5,
        )
    except WaitTimeoutError as error:
        print(error.run_id, error.last_run.status if error.last_run else "not observed")
    else:
        print(require_output(finished))

    latest = workflows.runs.get(run.id)
    page = workflows.runs.list(
        deployment=deployment,
        status="failed",
        limit=20,
        offset=0,
    )
```

The asynchronous methods accept the same arguments; await each operation.
Choose a new job ID for each logical start and persist it with the job. Reuse it
when recovering the same start after a process restart.

- `wait_for_completion` defaults to 600 seconds, starting at one-second polling delays
  and increasing up to five seconds. It returns succeeded, failed and interrupted
  runs normally.
- One observation deadline bounds all reads, retries/backoff and poll sleeps. Expiry
  raises WaitTimeoutError with the last observed `last_run`, or None if the first
  read did not finish. A shorter request timeout remains APITimeoutError.
- Observation timeout/cancellation leaves an accepted server-side run alive.
  No cancel, task or document API stubs are exposed.
- Lists contain newest-first summaries without output/result. None pagination fields
  are omitted; an explicit zero is sent for the server to validate.

List filters are `version_id`, `deployment`, `status`, `limit` and `offset`. The server defaults to
limit 50 and offset 0; supported ranges are 1–100 and 0–1,000,000 respectively.
Pages expose `items`, `limit` and `offset`, with no total or next-cursor field.
Advance offset by the number of returned items; an empty or short page ends the scan.
Each page reflects the server's current history.

## Results and types

Pydantic resources use Python names (`config_version_id`, `created_at`, `amount_usd`)
with the original API aliases (`configVersionID`, `createdAt`, `amountUsd`). Parameters
`deployment` or `version_id`, and `input`, become `deployment` or `configVersionID`, and
`additional`; omitted input sends `{}`.

`model_dump(by_alias=True, mode="json", exclude_none=True)` emits wire names and ISO timestamps. Datetime
fields parse ISO timestamps, billing amounts remain decimal strings, and `model_extra`
retains additive server fields. Required resource fields/types are checked; malformed
success responses raise InvalidResponseError.

Run statuses are `queued`, `running`, `succeeded`, `failed` and `interrupted`.
`traceport_ai.workflows` exports `WorkflowRun`, `WorkflowRunPage`, `WorkflowStep`,
`WorkflowRunBilling`, `WorkflowResult` and their status/mode aliases. Optional billing
receipts retain the payment method, period, currency, decimal amount and optional
credit timestamp. The SDK-derived `result` field is excluded from wire serialization.

Workflow-specific values use generic JSON (`Any`, dict/list). Result output selects
non-empty `data.final`, otherwise the full `data` map. `data`, `steps` and failed partial
output remain available. Run `output` retains the stored body and `result` interprets
it using the same rules as Execute. Unrecognized stored-output objects remain readable
without a derived result.

Use `result.require_output()`, `run.require_output()` or `traceport_ai.workflows.require_output` to opt into
WorkflowFailedError. A failed exception retains the partial result and optional run ID.
Successful summaries without output must first be read with runs.get.

Using the result from the execution example, an application-specific decoder can
validate and type its output. Decoder exceptions propagate unchanged:

```python
from pydantic import BaseModel
from traceport_ai.workflows import require_output


class AnswerModel(BaseModel):
    answer: str


output = require_output(result)
answer = require_output(result, AnswerModel.model_validate)
```

## Idempotency and retries

Execute and runs.start always send an Idempotency-Key. Without a supplied key, the SDK
generates a UUID per call and reuses it and the serialized body across retries. Persist
your own key to recover safely across process restarts or caller timeouts. Keys are
1–200 UTF-8 bytes with no whitespace/control characters.

Connection/body I/O failures and HTTP 408, 429, 500, 502, 503 and 504 are retried with
exponential backoff and jitter. Retry-After seconds/dates are honored, capped at one minute.
Reads and runs.start also retry request timeouts. **A client-side execute timeout is
never retried** in either Python client: the workflow may still be running. HTTP 408
responses follow the status-code policy above. Cancellation never retries. The default
two retries allow up to three attempts.

Changed input under the same key raises ConflictError. In-progress synchronous replay
exposes `existing_run_id` when reported by the backend; read that run instead of polling
the execute endpoint. A finished replay returns its saved result.

## Errors

```python
from traceport_ai import APIError, NotFoundError, Traceport
from traceport_ai.workflows import Workflows

with Traceport() as client:
    try:
        run = Workflows(client).runs.get("<run-id>")
    except NotFoundError:
        print("run missing from this organization")
    except APIError as error:
        print(error.status, error.error_code, error.request_id, str(error))
```

HTTP errors: BadRequestError (400), AuthenticationError (401), PaymentRequiredError
(402), PermissionDeniedError (403), NotFoundError (404), ConflictError (409),
RateLimitError (429), InternalServerError (5xx); other statuses use APIError.
Each retains `status`, `error_code`, `headers`, `body`, optional `request_id` and `retryable`.
`request_id` is None when the server omits `x-request-id`, and `error_code` can be empty.

Error types follow the HTTP status actually returned by the server. The synchronous
execute endpoint currently uses HTTP 409 for some validation/not-found errors, often
with an empty error code; a missing version does not always produce NotFoundError on
that endpoint. The SDK preserves the server response.

Other SDK errors: APIConnectionError, APITimeoutError, RequestAbortedError and
InvalidResponseError from `traceport_ai`, and WorkflowFailedError and WaitTimeoutError from
`traceport_ai.workflows`. All extend TraceportError;
network exceptions preserve their underlying `__cause__`. Async task cancellation and
invalid local arguments retain their native Python exception semantics.

## Package layout and verification

```text
python/
  pyproject.toml, uv.lock
  src/traceport_ai/
    __init__.py, _client.py, py.typed   # shared clients, options and request errors
    _core/                      # shared configuration, errors and HTTP
    workflows/                  # workflows product: sync/async classes, types and results
  tests/                        # shared fixtures, contracts and regressions
  examples/
  scripts/check_package.py
```

```sh
uv run --locked --all-extras ruff check .
uv run --locked --all-extras ruff format --check .
uv run --locked --all-extras mypy
uv run --locked --all-extras pytest --cov=traceport_ai
uv build
uv run --locked --all-extras twine check dist/*
uv run --locked --all-extras python scripts/check_package.py dist/*.whl
```

The package checker inspects typing/license/dependency metadata and installs the wheel
into an isolated consumer environment, then exercises sync and async imports/execution
with mocked HTTP. Builds produce a wheel and source distribution; ordinary tests make
no live calls. Clone the full SDK repository to run its shared-fixture tests.

Opt-in sandbox conformance (real executions consume workflow usage):

```sh
export TRACEPORT_API_KEY="<sandbox-key>"
export TRACEPORT_BASE_URL="http://localhost:1010/v1"
export TRACEPORT_CONFORMANCE_VERSION_OK="<successful-version>"
export TRACEPORT_CONFORMANCE_VERSION_FAIL="<deliberately-failing-version>"
uv run --locked --all-extras python examples/live_check.py
uv run --locked --all-extras python examples/live_check.py --async-client
```

These examples cover shared C-01–C-08 plus synchronous replay. C-07 explicitly reports
SKIP if the run is already terminal on the first read. Live verification, hosted CI,
registry ownership and publication are tracked separately from local implementation.

## License

[Apache License 2.0](https://github.com/traceport-ai/sdks/blob/main/LICENSE)
