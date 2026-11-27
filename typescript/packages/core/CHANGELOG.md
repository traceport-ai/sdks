# Changelog

## 0.0.1 (Unreleased)

Initial release of `@traceport/core`. This version has not been published.

### Client and configuration

- Server-side `Traceport` client for Node.js 20+, using standard Fetch APIs and no runtime dependencies. One client serves every Traceport product package.
- API key and `/v1` base URL configuration through options or `TRACEPORT_API_KEY` / `TRACEPORT_BASE_URL`.
- Custom `fetch`, default/per-request headers, request timeouts, retry limits and `AbortSignal` cancellation.
- `withOptions` derived clients that keep credentials, base URL and `fetch` while changing timeouts, retries or default headers.
- Browser-use guard with explicit `dangerouslyAllowBrowser` opt-in.

### Reliability and errors

- Generated or caller-supplied idempotency keys and stable serialized request bodies across retries.
- Automatic retries for connection/body I/O failures and HTTP 408, 429, 500, 502, 503 and 504, with jittered backoff and capped `Retry-After` support.
- Request timeouts and cancellation through response-body reads.
- Protected Authorization/Idempotency-Key headers and validation of client and request settings.
- Typed HTTP, connection, timeout, cancellation and response errors; HTTP errors retain response metadata and an optional request ID. In-progress replay run IDs on `ConflictError`.

### Distribution

- ESM and CommonJS builds with shared chunks, matching declarations and source maps.
- `@traceport/core/internal` entry for Traceport product packages (not public API).
