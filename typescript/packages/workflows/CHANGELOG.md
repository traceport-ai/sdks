# Changelog

## 0.1.0 (Unreleased)

Initial release of `@traceport/workflows`. This version has not been published. Requires `@traceport/core` ^0.1.0 (peer dependency).

### Workflows and results

- `Workflows` product constructed from a `@traceport/core` client.
- `workflows.execute` for synchronous execution of published workflow versions; a timed-out `execute` is not retried.
- `workflows.runs.start`, `get` and `list` for durable runs, including version/status filters and offset pagination.
- `workflows.runs.waitForCompletion` with configurable observation timeout, request timeout and polling intervals; observation deadlines cover reads, retries and poll delays.
- Typed run, step, page and billing-receipt models, with raw workflow data and stored output.
- Workflow failures returned as normal `failed` results, retaining partial output and executed steps.
- Final-output selection with a full-data fallback and `requireOutput` with optional schema decoding.
- `WorkflowFailedError` and `WaitTimeoutError` (with the last observed run when available).

### Distribution and examples

- ESM and CommonJS builds that import `@traceport/core` rather than bundling it.
- Execute, durable-run and opt-in live-conformance examples, shared fixture/contract tests and package checks.

Live API verification and registry/publication gates remain pending.
