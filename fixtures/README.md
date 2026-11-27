# Fixtures

Shared request/response cases. Every SDK loads these files in its unit tests, serves the response from a mocked transport, and asserts the expected outcome. One fixture describes one HTTP exchange.

Fixtures should be recorded from real workflow runs against a Traceport API, then sanitized: replace IDs with stable fake UUIDs and remove real prompts, outputs, keys and organization data. Until a recording exists, a fixture may be derived from the backend handler code; its `source.kind` is then `derived` and names the files it was derived from. Replace derived fixtures with recordings when a live server is available.

The current 19 cases are recordings from 13 November 2026. Eighteen came from the
running local Docker API, using separate synthetic organizations, keys and published
Start → Transform → End workflows, with no model/provider calls. They include normal
and empty-final success, an End-expression failure retaining partial Transform output,
running and terminal reads, pagination, same-key replay/conflict, authentication,
funding/quota errors, and the different missing-version responses from execute/start.
The 503 case came from a separate local HTTP backend with real authentication,
repositories and usecases, whose dispatcher was deliberately left unstarted. Its
`source.capture` identifies that setup; the main API was not stopped. Sandbox keys
were revoked after capture. These recordings do not certify deployed behavior or
replace the SDK live-conformance gate.

Five deployment-code cases are derived, not recorded: execute and start by
`deployment`, list filtered by `deployment`, and the 404 `deployment_not_found` and
409 `deployment_empty` errors. They come from the uncommitted `feat/workflow_deployment`
backend (MGMT-08), which no running server serves yet. Record them over HTTP once one
does, and replace the derived files.

## Recording another exchange

Use only synthetic workflows and values. The recorder preserves business data and
error text; UUID/key replacement cannot safely anonymize arbitrary customer content.
Use a dedicated sandbox for real executions, which consume workflow usage.

Create a private request JSON file outside the repository containing `method`, `path`,
optional `headers` (only `Idempotency-Key`) and optional JSON `body`. Use actual sandbox
IDs in that file. Match the existing fixture's scenario and HTTP/lifecycle status.
For a replay, reuse the original start's key and body; for a run read, supply its ID.
Then, from the repository root:

```sh
export TRACEPORT_API_KEY="<sandbox-key>"
curl --fail --silent --show-error http://localhost:1010/v1/docs/openapi.json \
  --output /private/tmp/traceport-server-openapi.json
shasum -a 256 /private/tmp/traceport-server-openapi.json
python3 scripts/record_fixture.py fixtures/workflows/execute/succeeded.json \
  --request /private/tmp/traceport-synthetic-request.json \
  --base-url http://localhost:1010 \
  --source "<server build/reference and synthetic scenario>" \
  --server-spec-sha256 "<digest from shasum>"
python3 scripts/validate_repo.py
python3 -m unittest discover -s scripts -p 'test_*.py'
```

The script makes exactly one HTTP request with no retries or redirects. It does not
store Authorization, cookies or arbitrary response headers; only Content-Type,
Location and Retry-After are retained. It replaces UUIDs consistently in paths,
payloads, map keys and error messages, and normalizes the idempotency key. It refuses
unexpected HTTP/outcome/lifecycle statuses and detected credential echoes. Review the
entire diff for private text and replay all SDK fixture suites before committing.

## Layout

```
fixtures/<namespace>/<operation-group>/<case>.json
fixtures/workflows/execute/failed_http200.json
fixtures/workflows/runs/start_replay_200.json
```

## Format

```json
{
  "name": "workflows.runs.start.replay_200",
  "description": "Same key and body returns the original run with HTTP 200.",
  "source": {
    "kind": "derived",
    "from": "traceport-apis@<commit> internal/transport/http/handlers/workflow_runs.go"
  },
  "operation": "startWorkflowRun",
  "request": {
    "method": "POST",
    "path": "/v1/workflow/runs",
    "headers": { "Idempotency-Key": "fixture-start-1" },
    "body": {
      "configVersionID": "00000000-0000-4000-8000-000000000001",
      "additional": {}
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Location": "/v1/workflow/runs/00000000-0000-4000-8000-000000000002"
    },
    "body": {
      "data": {
        "id": "00000000-0000-4000-8000-000000000002",
        "status": "succeeded"
      },
      "error": "",
      "status": 200,
      "errorCode": ""
    }
  },
  "expect": {
    "kind": "resource",
    "resource": {
      "id": "00000000-0000-4000-8000-000000000002",
      "status": "succeeded"
    }
  }
}
```

| Field                            | Rule                                                                                                                                                                                                      |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`                           | Unique across all fixtures.                                                                                                                                                                               |
| `source.kind`                    | `recorded` (captured over HTTP) or `derived` (written from backend code). `source.from` describes the server/build and setup.                                                                             |
| `source.recordedAt`              | Required for recordings: a timezone-aware ISO timestamp of the actual capture.                                                                                                                            |
| `source.capture`                 | `live-http` for the running API, or `isolated-backend-http` for a separately configured real backend; never label mocked handlers as recordings.                                                          |
| `source.serverSpecSha256`        | Required for `live-http`: SHA-256 of that running server's OpenAPI document. It can differ from the newer checked-in documentation snapshot. Isolated captures identify the backend commit/setup instead. |
| `operation`                      | An `operationId` in `contract/public-operations.json`.                                                                                                                                                    |
| `request.method`, `request.path` | Must match that operation in `contract/openapi.json`. Path parameters and query strings are filled in.                                                                                                    |
| `request.headers`                | Never include `Authorization` or `x-api-key`; the SDK transport adds credentials.                                                                                                                         |
| `response.status`                | A status code the operation documents.                                                                                                                                                                    |
| `expect.kind`                    | `resource` (unwrapped data), `outcome` (a workflow result, including a failure returned with HTTP 200) or `error` (typed SDK error).                                                                      |
| `expect.resource`                | Fields of the unwrapped resource to compare. For lists: `itemCount`, `limit`, `offset`.                                                                                                                   |
| `expect.outcome`                 | Workflow result to compare: `status` (`succeeded` or `failed`), `output`, optional `error` and `stepCount`. Allowed on `outcome` fixtures and on finished run reads.                                      |
| `expect.error`                   | Required when `kind` is `error`: `class` (SDK error class name, the same in every language), `status`, `errorCode`, `retryable`, and optional `existingRunId`.                                            |

Expected values use the wire field names. Each SDK maps them to its own casing.

`scripts/validate_repo.py` enforces these rules.
