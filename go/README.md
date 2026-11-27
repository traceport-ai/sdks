# Traceport Go SDK

Standard-library-only Go SDK for the Traceport API. Requires Go 1.22+.

**Status: 0.0.1, early release.** The API may change before 1.0. The module path is
`github.com/traceport-ai/sdks/go`.

The SDK is modular: one shared client and a package per product. Go compiles only the
packages you import, so using workflows pulls in nothing else.

| Package | Import path | Contents |
| --- | --- | --- |
| `traceport` | `github.com/traceport-ai/sdks/go` | The shared `Client`, options and request errors. |
| `workflows` | `github.com/traceport-ai/sdks/go/workflows` | Execute saved workflows and manage durable runs. |

Document parsing will ship as a `documents` package that takes the same client.

Use a Traceport API key and an active, published workflow version. This release
supports workflow execution and durable runs; document parsing, Human input, events
and workflow cancellation are not included. See the [changelog](https://github.com/traceport-ai/sdks/blob/main/go/CHANGELOG.md)
for the complete first-release feature set.

## Install

```bash
go get github.com/traceport-ai/sdks/go@v0.0.1
```

This one module contains the shared client and every product package. Release tags have
the `go/` prefix because the module lives in the repository's `go/` folder, for example
`go/v0.0.1`.

To try unreleased changes from a checkout, point your application's `go.mod` at it:

```text
replace github.com/traceport-ai/sdks/go => /absolute/path/to/sdks/go
```

## Execute a workflow

```go
package main

import (
	"context"
	"fmt"
	"log"

	traceport "github.com/traceport-ai/sdks/go"
	"github.com/traceport-ai/sdks/go/workflows"
)

func main() {
	client, err := traceport.NewClient() // TRACEPORT_API_KEY; optional TRACEPORT_BASE_URL
	if err != nil {
		log.Fatal(err)
	}
	wf := workflows.New(client) // other products take the same client

	result, err := wf.Execute(context.Background(), workflows.StartParams{
		Deployment: "support-triage-prod", // or VersionID: "<workflow-version-id>"
		Input:      map[string]any{"question": "What is Traceport?"},
	})
	if err != nil {
		log.Fatal(err)
	} // request failure
	if result.Status == workflows.RunFailed {
		log.Printf("workflow failed: %s; partial output: %v", result.Error, result.Output)
		return
	}
	fmt.Println(result.Output)
}
```

A workflow that ran and failed is a normal result. `result.RequireOutput()` opts into
a `*workflows.FailedError`, retaining partial output in its `Result`.

`Output` selects non-empty `data.final`, falling back to the complete `data` map.
`Data` and `Steps` retain execution details. Workflow-specific values use `any` and
`map[string]any`; validate/decode them with your application's schema. Step `Raw`
retains every wire field, including usage, dependencies, branches and tool calls.

### Supported methods

| Method                             | Purpose                                             |
| ---------------------------------- | --------------------------------------------------- |
| `wf.Execute`                       | Run a published version and wait for its outcome.   |
| `wf.Runs.Start`                    | Start a durable background run and return its ID.   |
| `wf.Runs.Get`                      | Read a run, including stored output when available. |
| `wf.Runs.List`                     | Read a page of run summaries.                       |
| `wf.Runs.WaitForCompletion`        | Poll an existing run to a terminal status.          |

`wf` is `workflows.New(client)`.

## Configuration

This fragment uses `net/http` and `time` in addition to the `traceport` import:

```go
client, err := traceport.NewClient(
	traceport.WithAPIKey("<key>"),
	traceport.WithBaseURL("https://api.traceport.ai/v1"),
	traceport.WithTimeout(60*time.Second),
	traceport.WithMaxRetries(2), // zero disables automatic retries
	traceport.WithHTTPClient(&http.Client{}),
	traceport.WithDefaultHeaders(http.Header{"X-Team": {"search"}}),
)
```

Defaults: `TRACEPORT_API_KEY`, `TRACEPORT_BASE_URL` then `https://api.traceport.ai/v1`,
60 seconds per attempt and two retries. Execute uses at least six minutes by default
to accommodate the server's synchronous execution budget. The same client can be
shared by goroutines; configure it before use. Retries and backoff can extend a
logical call beyond one request timeout; the observation timeout in WaitOptions
is the overall polling budget.

Every API method accepts a context and optional `WithRequestTimeout`,
`WithRequestMaxRetries` and `WithHeaders`. A per-request timeout overrides Execute's
six-minute minimum. Durations must be positive and retry counts non-negative;
invalid settings return `*ValidationError` before HTTP is sent.

Timeout and cancellation stay active through the entire response body. Cancelling
the caller's context returns `*RequestAbortedError`; the underlying context cause
remains accessible through `errors.Is`. If you inject an `http.Client`, its transport
must honor request contexts. Its own `Timeout`, if set, can shorten the SDK timeout.

Authorization and Idempotency-Key cannot be replaced through extra headers.
Set keys with `WithAPIKey` and `WithIdempotencyKey` respectively.
Supply your own `http.Client` when your application needs to control its connection
pool or call `CloseIdleConnections`; the SDK has no separate Close method.

### Derived clients

`client.WithOptions(...)` returns a client with the same API key, base URL and HTTP
client (so the same connection pool), and different timeouts, retries or default
headers. Use it to give one product different settings without a second client:

```go
patient, err := client.WithOptions(traceport.WithTimeout(5*time.Minute), traceport.WithMaxRetries(5))
if err != nil {
	return err
}
wf := workflows.New(patient)
```

Only `WithTimeout`, `WithMaxRetries` and `WithDefaultHeaders` are accepted; default
headers are merged over the original's. Options that would change the key, base URL
or HTTP client return `*ValidationError`. The original client is unchanged.

## Durable runs

### Deployment codes or version IDs

Set exactly one of:

- `Deployment` (recommended): a stable code such as `"support-triage-prod"`, created on the
  workflow's Deployments tab in the dashboard. The server runs whichever version is deployed
  to it, so shipping a new version needs no change in your code. An unknown code returns a
  not-found error (`deployment_not_found`); a code with nothing deployed returns a conflict
  error (`deployment_empty`).
- `VersionID`: pins one exact version. It must be live (deployed to at least one code).

Setting both or neither returns `*traceport.ValidationError` before any request is sent.
Runs started by code carry it in `Run.Deployment`.

Inside a function returning `error`, using `wf := workflows.New(client)` and application
values `ctx`, `deployment` and a persisted `jobID`:

```go
run, err := wf.Runs.Start(ctx, workflows.StartParams{
	Deployment: deployment,
	Input:      map[string]any{"question": "Hello"},
}, traceport.WithIdempotencyKey(jobID)) // persist one key per logical job
if err != nil {
	return err
}
// Persist run.ID so another process can read it later.

finished, err := wf.Runs.WaitForCompletion(ctx, run.ID,
	workflows.WaitOptions{Timeout: 2 * time.Minute},
	traceport.WithRequestTimeout(10*time.Second),
)
if err != nil {
	return err
}
output, err := finished.RequireOutput()
if err != nil {
	return err
}
fmt.Println(output)

latest, err := wf.Runs.Get(ctx, run.ID)
if err != nil {
	return err
}
page, err := wf.Runs.List(ctx, workflows.ListRunsParams{
	Deployment: deployment,
	Status:     workflows.RunFailed,
	Limit:      workflows.Int(20),
	Offset:     workflows.Int(0),
})
if err != nil {
	return err
}
fmt.Println(latest.Status, len(page.Items))
```

- `Deployment` or `VersionID`, and `Input`, map to the API's `deployment` or `configVersionID`, and `additional`.
  A nil Input sends `{}`. Other resource fields use Go casing with the original JSON tags.
- Get and WaitForCompletion return failed and interrupted runs normally. Check `Status`
  or call `RequireOutput` to opt into a workflow failure error.
- WaitForCompletion defaults to ten minutes, with polling delays starting at one second
  and growing to five seconds. `WaitOptions` zero fields select defaults; negative fields
  are invalid. `PollInterval` and `MaxPollInterval` are configurable.
- One observation deadline bounds requests, retries/backoff and poll sleeps. Expiry returns
  `*WaitTimeoutError` with `RunID` and the last observed `LastRun`, which is nil if the
  first read did not finish. Context cancellation stays a distinct request-aborted error.
- Observation timeout/cancellation leaves an accepted run alive. There is no cancel API yet.
- List returns newest-first summaries without Output/Result. Nil Limit/Offset omit those
  filters; `Int(0)` sends an explicit zero and lets the server validate it.
- A finished run's stored `Output` is interpreted as `Result` using the same rules as Execute.
  Unrecognized stored-output objects remain readable with a nil Result. Run `Raw` retains
  additive fields from the server.

List filters are `VersionID`, `Deployment`, `Status`, `Limit` and `Offset`. The server defaults to
limit 50 and offset 0; supported ranges are 1–100 and 0–1,000,000 respectively.
Pages expose `Items`, `Limit` and `Offset`, with no total or next-cursor field.
Advance Offset by the number of returned items; an empty or short page ends the scan.
Each page reflects the server's current history.

Run statuses are `RunQueued`, `RunRunning`, `RunSucceeded`, `RunFailed` and
`RunInterrupted`. Resources use `time.Time` / `*time.Time` timestamps; billing amounts
remain decimal strings. Generic workflow values follow `encoding/json` conventions,
including `float64` JSON numbers. Validate/decode them into application-specific types
when needed. Billing receipts are optional and retain their original method, period,
currency, amount and optional credit timestamp.

## Idempotency and retries

Execute and Runs.Start always send an Idempotency-Key. The SDK generates a random UUID
when no key is supplied and preserves that key and the serialized body across retries.
Persist your own key to safely retry across process restarts. Keys must be 1–200 bytes
without whitespace/control characters. Reusing a key with changed input returns ConflictError.

The retry policy matches TypeScript: connection failures (including interrupted response
bodies), HTTP 408, 429, 500, 502, 503 and 504; default two retries, exponential backoff
with jitter and Retry-After support. Server retry delays are capped at one minute.
Reads and Runs.Start retry request timeouts. Execute never retries a client timeout:
the workflow may still be running. HTTP 408 responses follow the status-code policy
above. Cancellation is never retried. The default two retries allow up to three attempts.

An in-progress synchronous replay returns ConflictError with ExistingRunID when the backend
includes the original run ID. Poll that run with Runs.Get. A terminal replay returns its result.

## Errors

Use `errors.As` for typed errors:

```go
var notFound *traceport.NotFoundError
var apiError *traceport.APIError
var waitTimeout *workflows.WaitTimeoutError
if errors.As(err, &waitTimeout) {
	log.Printf("observation timed out for run %s", waitTimeout.RunID)
	if waitTimeout.LastRun != nil {
		log.Printf("last status: %s", waitTimeout.LastRun.Status)
	}
} else if errors.As(err, &notFound) {
	// Run or version missing from this organization.
} else if errors.As(err, &apiError) {
	log.Printf("status=%d code=%s requestID=%s: %s",
		apiError.StatusCode, apiError.ErrorCode, apiError.RequestID, apiError.Message)
}
```

HTTP subclasses: BadRequestError (400), AuthenticationError (401), PaymentRequiredError
(402), PermissionDeniedError (403), NotFoundError (404), ConflictError (409), RateLimitError
(429), InternalServerError (5xx). Other statuses use APIError. All expose the common
APIError through `errors.As`, with StatusCode, ErrorCode, Headers, Body, RequestID and Retryable.
RequestID is empty when the server omits `x-request-id`, and ErrorCode can be empty.

Error types follow the HTTP status actually returned by the server. The synchronous
execute endpoint currently uses HTTP 409 for some validation/not-found errors, often
with an empty error code; a missing version does not always produce NotFoundError on
that endpoint. The SDK preserves the server response.

Other error types: ValidationError, APIConnectionError, APITimeoutError,
RequestAbortedError, InvalidResponseError, FailedError and WaitTimeoutError.
Network/cancellation errors preserve their underlying causes through `errors.Is`/`errors.As`.
Observation expiry also matches `context.DeadlineExceeded`; use `errors.As` to
distinguish WaitTimeoutError from a request timeout or caller deadline.

## Package layout

```text
go/
  client.go, options.go, errors.go, doc.go   # Package traceport: shared client, options, errors
  workflows/                                 # Package workflows: execute, runs, polling, models
  internal/core/                             # Shared HTTP, options, errors and validation
  test/                                      # Public-API, contract and shared-fixture tests
  examples/
  go.mod
```

Applications import `github.com/traceport-ai/sdks/go` for the client and each product
package they use. Products reach the shared transport through `internal/core`, which
applications cannot import. One module versions every package together. See the official
[module layout](https://go.dev/doc/modules/layout) and
[publishing](https://go.dev/doc/modules/publishing) guides.

## Development

From `go/` in a full checkout of the SDK repository, which supplies the shared
contract and fixtures:

```sh
gofmt -w .
go vet ./...
go test -race -coverpkg=.,./internal/... ./...
go build ./...
```

Tests replay the shared contract/fixtures and use controlled HTTP transports; they make no
live API calls. Examples compile during tests and build:

```sh
export TRACEPORT_API_KEY="<sandbox-key>"
export TRACEPORT_VERSION_ID="<published-workflow-version-id>"
go run ./examples/execute
export TRACEPORT_JOB_ID="<persisted-logical-job-id>"
go run ./examples/start-and-wait
```

Explicit sandbox conformance (real executions consume workflow usage):

```sh
TRACEPORT_BASE_URL=http://localhost:1010/v1 \
TRACEPORT_API_KEY="<sandbox-key>" \
TRACEPORT_CONFORMANCE_VERSION_OK="<successful-version>" \
TRACEPORT_CONFORMANCE_VERSION_FAIL="<deliberately-failing-version>" \
go run ./examples/live-check
```

This exercises C-01 through C-08 from the shared conformance spec, plus synchronous replay.
C-07 reports SKIP if the workflow already finished on its first poll. Never use production
keys or workflows for conformance. Publication and live verification are separate release gates.

## License

[Apache License 2.0](https://github.com/traceport-ai/sdks/blob/main/LICENSE)
