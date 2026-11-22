/**
 * HTTP transport shared by every resource.
 *
 * Responsibilities:
 *  - build URLs and headers (auth, User-Agent, idempotency key);
 *  - enforce per-request timeouts and the caller's AbortSignal;
 *  - unwrap the `{ data, error, status, errorCode }` response envelope;
 *  - map failures to typed errors;
 *  - retry transient failures with the same body and idempotency key.
 */

import {
  APIConnectionError,
  APIError,
  APITimeoutError,
  InvalidResponseError,
  RequestAbortedError,
} from "./errors.js";
import { isBrowser, isRecord, sleep, withSignal } from "./runtime.js";
import { validateMaxRetries, validateTimeout } from "./validation.js";
import { VERSION } from "./version.js";

/** A `fetch` implementation. Defaults to the global `fetch`. */
export type Fetch = typeof globalThis.fetch;

/** Options accepted by every SDK method. */
export interface RequestOptions {
  /** Cancels the request. Cancelling never retries. */
  signal?: AbortSignal;
  /** Timeout for this request in milliseconds. Overrides the client `timeout`. */
  timeout?: number;
  /** Maximum automatic retries for this request. Overrides the client `maxRetries`. */
  maxRetries?: number;
  /** Extra headers, for example `traceparent`. Cannot override Authorization or Idempotency-Key. */
  headers?: Record<string, string>;
}

/** Options for methods that start work on the server. */
export interface MutationRequestOptions extends RequestOptions {
  /**
   * Idempotency key for this logical operation. The SDK generates one when omitted and reuses it
   * on every retry. Pass your own (and store it) to safely retry across process restarts.
   * At most 200 bytes, without whitespace or control characters.
   */
  idempotencyKey?: string;
}

/** Fully resolved client settings used by the transport. */
export interface TransportConfig {
  apiKey: string;
  baseURL: string;
  timeout: number;
  maxRetries: number;
  fetch: Fetch;
  defaultHeaders: Record<string, string>;
}

/** One logical API call, possibly sent several times. */
export interface APIRequest {
  method: "GET" | "POST";
  /** Path relative to the base URL, for example `/workflow/runs`. */
  path: string;
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  idempotencyKey?: string;
  /**
   * Whether a timed-out attempt may be retried. False for synchronous execution: the server keeps
   * running after a client timeout, so a retry would only report the run as still in progress.
   */
  retryOnTimeout: boolean;
  /**
   * Minimum default timeout for this operation, for calls that legitimately take longer than
   * ordinary requests. The effective default is the larger of this and the client timeout; a
   * per-call `timeout` still wins.
   */
  minimumTimeout?: number;
  options?: RequestOptions | undefined;
}

/** A successful, unwrapped response. */
export interface APIResponse<T> {
  /** The envelope's `data` field. */
  data: T;
  /** HTTP status code (for example 200 or 202). */
  status: number;
  headers: Headers;
}

/** Retry-After values larger than this are capped, so a bad header cannot stall a caller. */
const MAX_RETRY_AFTER_MS = 60_000;
const INITIAL_BACKOFF_MS = 500;
/** Abort reasons that tell a timeout apart from a caller cancellation. */
const TIMEOUT_REASON = Symbol("traceport.timeout");
const CALLER_ABORT_REASON = Symbol("traceport.callerAbort");
const MAX_BACKOFF_MS = 8_000;

/** Sends requests to the Traceport API. Internal; use the {@link Traceport} client instead. */
export class Transport {
  constructor(private readonly config: TransportConfig) {}

  /** Sends `request`, retrying transient failures, and returns the unwrapped envelope data. */
  async request<T>(request: APIRequest): Promise<APIResponse<T>> {
    const options = request.options ?? {};
    const maxRetries = options.maxRetries ?? this.config.maxRetries;
    const timeout = options.timeout ?? Math.max(request.minimumTimeout ?? 0, this.config.timeout);
    validateTimeout(timeout, "timeout");
    validateMaxRetries(maxRetries);
    const url = this.buildURL(request.path, request.query);
    const headers = this.buildHeaders(request);
    // Serialize once so every retry sends byte-identical content under the same idempotency key.
    const body = request.body === undefined ? undefined : JSON.stringify(request.body);

    for (let attempt = 0; ; attempt++) {
      const canRetry = attempt < maxRetries;
      let received: { response: Response; body: unknown };
      try {
        received = await this.send(
          url,
          { method: request.method, headers, body },
          timeout,
          options.signal,
        );
      } catch (error) {
        if (error instanceof RequestAbortedError) throw error;
        const retryable = !(error instanceof APITimeoutError) || request.retryOnTimeout;
        if (canRetry && retryable) {
          await sleep(backoffDelay(attempt), options.signal);
          continue;
        }
        throw error;
      }

      const { response, body: responseBody } = received;
      if (response.ok) return parseSuccess<T>(response, responseBody);

      const apiError = parseFailure(response, responseBody);
      if (canRetry && apiError.retryable) {
        await sleep(retryDelay(response.headers, attempt), options.signal);
        continue;
      }
      throw apiError;
    }
  }

  /** Sends and reads one attempt within its timeout, translating I/O failures into SDK errors. */
  private async send(
    url: string,
    init: { method: string; headers: Headers; body: string | undefined },
    timeout: number,
    signal: AbortSignal | undefined,
  ): Promise<{ response: Response; body: unknown }> {
    if (signal?.aborted) {
      throw new RequestAbortedError("request was aborted", { cause: signal.reason });
    }
    // One controller cancels the fetch on either the caller's signal or our timeout. The abort
    // reason records which side cancelled, so the error says "timed out" or "aborted" correctly.
    const controller = new AbortController();
    const timer = setTimeout(() => {
      controller.abort(TIMEOUT_REASON);
    }, timeout);
    const onAbort = (): void => {
      controller.abort(CALLER_ABORT_REASON);
    };
    signal?.addEventListener("abort", onAbort, { once: true });

    try {
      const requestInit: RequestInit = {
        method: init.method,
        headers: init.headers,
        signal: controller.signal,
      };
      if (init.body !== undefined) requestInit.body = init.body;
      return await withSignal(controller.signal, async () => {
        const response = await this.config.fetch(url, requestInit);
        controller.signal.throwIfAborted();
        const body = await readBody(response);
        controller.signal.throwIfAborted();
        return { response, body };
      });
    } catch (error) {
      const reason: unknown = controller.signal.reason;
      if (reason === TIMEOUT_REASON) {
        throw new APITimeoutError(`request timed out after ${timeout} ms`, { cause: error });
      }
      if (reason === CALLER_ABORT_REASON) {
        throw new RequestAbortedError("request was aborted", { cause: signal?.reason });
      }
      throw new APIConnectionError("could not connect to the Traceport API", { cause: error });
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    }
  }

  private buildURL(path: string, query: APIRequest["query"]): string {
    const url = new URL(this.config.baseURL + path);
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
    return url.toString();
  }

  private buildHeaders(request: APIRequest): Headers {
    const headers = new Headers({
      Accept: "application/json",
      Authorization: `Bearer ${this.config.apiKey}`,
    });
    // Browsers forbid setting User-Agent; send it only where the runtime allows it.
    if (!isBrowser()) headers.set("User-Agent", userAgent());
    if (request.body !== undefined) headers.set("Content-Type", "application/json");
    if (request.idempotencyKey !== undefined) {
      headers.set("Idempotency-Key", request.idempotencyKey);
    }
    // Credentials and the resolved idempotency key belong to this operation, not header defaults.
    for (const source of [this.config.defaultHeaders, request.options?.headers ?? {}]) {
      for (const [key, value] of Object.entries(source)) {
        const name = key.toLowerCase();
        if (name !== "authorization" && name !== "idempotency-key") headers.set(key, value);
      }
    }
    return headers;
  }
}

/** `traceport-typescript/<version> <runtime>/<version>`, for server-side diagnostics. */
function userAgent(): string {
  const runtime = (globalThis as { process?: { versions?: { node?: string } } }).process?.versions
    ?.node;
  return `traceport-typescript/${VERSION}${runtime === undefined ? "" : ` node/${runtime}`}`;
}

/** Reads the body as JSON when possible, falling back to the raw text. */
async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.trim() === "") return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

/** Unwraps a 2xx envelope. A 2xx without a valid envelope is an {@link InvalidResponseError}. */
function parseSuccess<T>(response: Response, body: unknown): APIResponse<T> {
  if (!isRecord(body) || !("data" in body)) {
    throw new InvalidResponseError(
      "response is not a Traceport API envelope",
      response.status,
      body,
    );
  }
  // The backend always sends an empty `error` on success; treat anything else as malformed.
  if (typeof body.error === "string" && body.error.trim() !== "") {
    throw new InvalidResponseError(
      `response reported an error with HTTP ${response.status}: ${body.error}`,
      response.status,
      body,
    );
  }
  return { data: body.data as T, status: response.status, headers: response.headers };
}

/** Builds a typed error from a non-2xx response, using the envelope when there is one. */
function parseFailure(response: Response, body: unknown): APIError {
  const envelope = isRecord(body) ? body : {};
  const message =
    typeof envelope.error === "string" && envelope.error.trim() !== ""
      ? envelope.error
      : `request failed with HTTP ${response.status}`;
  const errorCode = typeof envelope.errorCode === "string" ? envelope.errorCode : "";
  return APIError.fromResponse({
    status: response.status,
    message,
    errorCode,
    headers: response.headers,
    body,
  });
}

/** Exponential backoff with jitter: about 0.5 s, 1 s, 2 s, … capped at 8 s. */
function backoffDelay(attempt: number): number {
  const base = Math.min(INITIAL_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
  // Up to 25% jitter spreads retries from many clients.
  return base * (1 - Math.random() * 0.25);
}

/** Honors `Retry-After` (seconds or an HTTP date) when present, otherwise uses backoff. */
function retryDelay(headers: Headers, attempt: number): number {
  const header = headers.get("retry-after");
  if (header !== null) {
    const seconds = Number(header);
    const ms = Number.isFinite(seconds) ? seconds * 1000 : Date.parse(header) - Date.now();
    if (Number.isFinite(ms) && ms >= 0) return Math.min(ms, MAX_RETRY_AFTER_MS);
  }
  return backoffDelay(attempt);
}
