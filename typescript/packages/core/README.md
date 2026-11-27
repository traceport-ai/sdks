# @traceport/core

The shared client for the [Traceport](https://traceport.ai) TypeScript SDK. It owns your API key, base URL, HTTP transport, retries, timeouts and error classes. Product packages such as [`@traceport/workflows`](https://github.com/traceport-ai/sdks/tree/main/typescript/packages/workflows) take this client, so one client serves every product.

> **Status: 0.0.1 pre-release, unpublished.**

- Server-side Node.js 20+, with a Fetch-based implementation for compatible Bun, Deno and edge runtimes.
- No runtime dependencies. ESM and CommonJS builds with type declarations.

## Usage

```ts
import { Traceport } from "@traceport/core";
import { Workflows } from "@traceport/workflows";

const client = new Traceport(); // reads TRACEPORT_API_KEY
const workflows = new Workflows(client);
```

## Configuration

```ts
const client = new Traceport({
  apiKey: "<key>", // omit to read TRACEPORT_API_KEY
  baseURL: "https://api.traceport.ai/v1", // default: TRACEPORT_BASE_URL, then this URL
  timeout: 60_000, // milliseconds per attempt; some product calls wait longer by default
  maxRetries: 2, // automatic retries for transient failures
  fetch: globalThis.fetch, // replace with your custom fetch implementation if needed
  defaultHeaders: { "x-team": "search" }, // sent with every request
});
```

Product methods accept per-call `signal`, `timeout`, `maxRetries` and `headers`. Timeouts apply per attempt and cover the complete response body; retries and backoff can extend a logical call. Timeouts must be finite, positive and at most 2,147,483,647 ms; `maxRetries` must be a non-negative safe integer. Invalid settings throw `TypeError` before any request. Extra headers cannot override `Authorization` or `Idempotency-Key`.

The client refuses to run in a web browser, because the API key would be visible to every visitor. Call Traceport from your server. `dangerouslyAllowBrowser: true` turns the check off.

The implementation needs Fetch APIs, `AbortController`, `TextEncoder` and `crypto.randomUUID`. Environment defaults are read through `process.env` when available; otherwise pass credentials and the base URL explicitly.

### Derived clients

`client.withOptions({ timeout, maxRetries, defaultHeaders })` returns a new client with the same credentials, base URL and `fetch`. Use it to give one product different settings without configuring a second client. `defaultHeaders` are merged over the original's. The original client is unchanged.

```ts
const patient = client.withOptions({ timeout: 300_000, maxRetries: 5 });
const workflows = new Workflows(patient);
```

## Idempotency and retries

- Product operations that start work always send an `Idempotency-Key`. Without your own key, a key is generated per call and reused on every retry of that call, with an identical body.
- Retried automatically (default 2 retries, up to 3 attempts): connection and response-body I/O failures and HTTP 408, 429, 500, 502, 503 and 504. Backoff includes jitter and honors `Retry-After` (seconds or an HTTP date), capped at one minute.
- 4xx errors other than 408 and 429 are never retried. Each product documents which timed-out operations are not retried.
- Supplied keys must be 1–200 bytes without whitespace or control characters.

## Errors

Every SDK error extends `TraceportError`. Product packages add their own (for example `WorkflowFailedError`) on top of these.

| Error                         | When                                                              |
| ----------------------------- | ----------------------------------------------------------------- |
| `BadRequestError` (400)       | Invalid request, for example a bad query parameter                |
| `AuthenticationError` (401)   | Missing, unknown, inactive or expired API key                     |
| `PaymentRequiredError` (402)  | Insufficient wallet credits                                       |
| `PermissionDeniedError` (403) | Plan does not allow it, or allowance exhausted                    |
| `NotFoundError` (404)         | Resource not found in your organization                           |
| `ConflictError` (409)         | Idempotency conflict, or the same request still running           |
| `RateLimitError` (429)        | Too many requests                                                 |
| `InternalServerError` (5xx)   | Server error or temporarily unavailable                           |
| `APIConnectionError`          | Connection or response-body I/O failure                           |
| `APITimeoutError`             | The request attempt, including body reading, exceeded its timeout |
| `RequestAbortedError`         | Cancelled through your `AbortSignal`                              |
| `InvalidResponseError`        | Success status with an unrecognized body                          |

`APIError` subclasses expose `status`, `errorCode`, `headers`, `body`, `retryable`, and `requestId` when the server returns `x-request-id`. Error codes can be empty. Error types follow the HTTP status the server actually returned.

```ts
import { APIError, NotFoundError } from "@traceport/core";

try {
  await workflows.runs.get("<run-id>");
} catch (error) {
  if (error instanceof NotFoundError) {
    // …
  } else if (error instanceof APIError) {
    console.error(error.status, error.errorCode, error.message);
  }
}
```

## For product packages

`@traceport/core/internal` exposes the shared transport (`transportOf(client)`) and helpers to Traceport product packages. It is not public API and not covered by semantic versioning; applications should not import it.

## License

[Apache License 2.0](https://github.com/traceport-ai/sdks/blob/main/LICENSE)
