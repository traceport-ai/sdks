# @traceport/workflows

Run saved [Traceport](https://traceport.ai) workflows synchronously, or as durable background runs. Uses the shared client from [`@traceport/core`](https://github.com/traceport-ai/sdks/tree/main/typescript/packages/core).

> **Status: 0.1.0 pre-release, unpublished.** Human input, events and run cancellation are not part of this version.

```sh
npm install @traceport/core @traceport/workflows   # after publication
```

`@traceport/core` is a peer dependency: you install it once and every Traceport product shares it.

## Quick start

```ts
import { Traceport } from "@traceport/core";
import { Workflows } from "@traceport/workflows";

const workflows = new Workflows(new Traceport()); // reads TRACEPORT_API_KEY

const result = await workflows.execute({
  versionId: "<workflow-version-id>",
  input: { question: "What is Traceport?" },
});

if (result.status === "succeeded") {
  console.log(result.output);
} else {
  console.error(result.error, result.output); // partial output
}
```

CommonJS: `const { Workflows } = require("@traceport/workflows");`.

Client configuration, retries and request errors are documented in `@traceport/core`.

| Method                             | Purpose                                             |
| ---------------------------------- | --------------------------------------------------- |
| `workflows.execute`                | Run a published version and wait for its outcome.   |
| `workflows.runs.start`             | Start a durable background run and return its ID.   |
| `workflows.runs.get`               | Read a run, including stored output when available. |
| `workflows.runs.list`              | Read a page of run summaries.                       |
| `workflows.runs.waitForCompletion` | Poll an existing run to a terminal status.          |

## Synchronous execution

`workflows.execute(params, options?)` runs a published workflow version and waits for its result. It waits at least 6 minutes by default (the server's limit is 5), or the client timeout if larger.

A workflow that runs and fails is **not** an exception: the call resolves with `status: "failed"`, the workflow error and any partial output. Exceptions are reserved for request problems.

| Field    | Meaning                                                                                       |
| -------- | --------------------------------------------------------------------------------------------- |
| `status` | `"succeeded"` or `"failed"`                                                                   |
| `output` | `data.final` when it has entries, otherwise the whole `data` map. Partial output when failed. |
| `error`  | Workflow error message, when failed                                                           |
| `data`   | Raw per-node-type results                                                                     |
| `steps`  | Every executed node, in order                                                                 |

To treat a failed workflow as an exception, use `requireOutput`:

```ts
import { requireOutput } from "@traceport/workflows";

const output = requireOutput(result);
// Throws WorkflowFailedError (with .result.output for partial output) when the workflow failed.

// AnswerSchema is your application's schema parser, for example a Zod schema.
const answer = requireOutput(result, (value) => AnswerSchema.parse(value));
```

`requireOutput` also accepts a run from `runs.get` or `waitForCompletion`. It throws for failed, interrupted and unfinished runs, and for summaries without interpreted output. Exceptions from your decoder propagate unchanged.

A client-side `execute` timeout is **not** retried, because the workflow may still be running. A later call with the same idempotency key returns `ConflictError` with `existingRunId` while it runs, and the stored result once it finishes. The synchronous endpoint currently returns HTTP 409 for some validation and not-found errors, often with an empty `errorCode`; the SDK reports what the server returned.

## Durable runs

Durable runs execute in the background. Start one, store its ID, and read it later.

```ts
const run = await workflows.runs.start(
  { versionId, input: { question: "Hi" } },
  { idempotencyKey: jobId }, // optional; persist it to retry safely across restarts
);

const finished = await workflows.runs.waitForCompletion(run.id, { timeout: 120_000 });
console.log(finished.status, finished.result?.output);

const latest = await workflows.runs.get(run.id);
const page = await workflows.runs.list({ versionId, status: "failed", limit: 20 });
```

Choose a new job ID for each logical start and persist it with the job; reuse it when recovering the same start after a restart. The same key with different input fails with `ConflictError`.

- `runs.get` returns failed and interrupted runs normally. Check `status`, or call `requireOutput(run)`.
- `runs.waitForCompletion` polls until `succeeded`, `failed` or `interrupted`. Its `timeout` bounds requests, retries and polling delays together. When it passes, it throws `WaitTimeoutError`; `lastRun` holds the last observed run, or `undefined` if the first read did not finish. The run keeps going; there is no cancel operation yet.
- `runs.list` returns summaries newest first; summaries have no `output` or `result`.
- Each run's `result` interprets its stored output the same way as `execute`.

Parameters use `versionId` and `input`; the SDK sends them as the API's `configVersionID` and `additional`. Run resources keep the API's field names.

### Polling and pagination

| Wait option       | Default        | Meaning                                                             |
| ----------------- | -------------- | ------------------------------------------------------------------- |
| `timeout`         | `600_000` ms   | Overall observation budget, including requests, retries and sleeps. |
| `requestTimeout`  | Client timeout | Timeout per `runs.get` attempt.                                     |
| `pollInterval`    | `1_000` ms     | Initial poll delay, capped by `maxPollInterval`.                    |
| `maxPollInterval` | `5_000` ms     | Maximum poll delay as polling backs off.                            |

`signal`, `headers` and `maxRetries` are forwarded to polling reads. Aborting stops polling and leaves the run alive.

List filters are `versionId`, `status`, `limit` and `offset`. The server defaults to `limit=50`, `offset=0`; supported ranges are 1–100 and 0–1,000,000. Pages contain `items`, `limit` and `offset`, with no total or cursor. Advance `offset` by the number of returned items; an empty or short page ends the scan.

### Resource types

Run statuses are `queued`, `running`, `succeeded`, `failed` and `interrupted`. `WorkflowRun`, `WorkflowRunPage`, `WorkflowStep` and `WorkflowRunBilling` are exported types. Timestamps remain ISO strings. Workflow inputs and outputs stay generic JSON; use a decoder for an application-specific output type. Unrecognized stored output remains available in `run.output` even when `run.result` cannot be derived.

## Workflow errors

These add to the request errors from `@traceport/core`:

| Error                 | When                                    |
| --------------------- | --------------------------------------- |
| `WorkflowFailedError` | Thrown only by `requireOutput`          |
| `WaitTimeoutError`    | Thrown only by `runs.waitForCompletion` |

## License

[Apache License 2.0](https://github.com/traceport-ai/sdks/blob/main/LICENSE)
