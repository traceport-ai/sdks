# Changelog

## 0.0.1

Initial release of module `github.com/traceport-ai/sdks/go`: package `traceport` (shared client)
and product package `workflows`.

### Client and configuration

- Standard-library-only Go 1.22+ client, safe for concurrent use after configuration.
- API key and `/v1` base URL configuration through functional options or `TRACEPORT_API_KEY` / `TRACEPORT_BASE_URL`.
- Injectable `http.Client`, default/per-request headers, request timeouts and retry limits.
- `context.Context` support on every operation, including cancellation and caller deadlines.
- One shared `Client` passed to product packages; `Client.WithOptions` derives a client with the same credentials, base URL and HTTP client but different timeouts, retries or default headers.

### Workflows and results

- `workflows.New(client)` product service; `Execute` for synchronous execution of published workflow versions.
- `StartParams.Deployment` runs whichever version is deployed to a stable code; `VersionID` pins one version. Exactly one is required (`*ValidationError` before sending otherwise). `Run.Deployment` and `ListRunsParams.Deployment` expose and filter by the code.
- `Runs.Start`, `Get` and `List` for durable runs, including version/status filters and offset pagination.
- `Runs.WaitForCompletion` with configurable observation timeout, request timeout and polling intervals.
- Typed run, step, status, mode, page and billing-receipt resources; native timestamps, decimal-string billing amounts and generic JSON workflow values.
- Original run/step fields retained in `Raw`, plus interpreted stored results and partial failed-workflow output.
- `RequireOutput` methods on workflow results and runs for opt-in workflow-failure errors.

### Reliability and errors

- Generated or caller-supplied idempotency keys and stable serialized request bodies across retries.
- Automatic retries for connection/body I/O failures and HTTP 408, 429, 500, 502, 503 and 504, with jittered backoff and capped `Retry-After` support.
- Full response-body timeout/cancellation and one observation deadline covering reads, retries and poll sleeps.
- Separate synchronous-execution timeout behavior: a timed-out `Execute` is not retried.
- Protected Authorization/Idempotency-Key headers and local argument/resource validation.
- Typed HTTP, connection, timeout, cancellation, validation, response, workflow-failure and wait-timeout errors with `errors.As` / `errors.Is` support.
- HTTP response metadata and optional request IDs, in-progress replay run IDs, and the last observed run on wait timeout when available.

### Distribution and examples

- One source module with a stable public package and internal core/workflow packages; version tags use the `go/v...` prefix.
- Execute, durable-run and opt-in live-conformance examples, plus shared fixture/contract tests and race-enabled checks.

Live API verification and versioned module publication remain pending.
