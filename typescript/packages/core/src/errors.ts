/**
 * Error classes thrown by the SDK.
 *
 * Every error extends {@link TraceportError}, so `catch (e) { if (e instanceof TraceportError) … }`
 * covers everything the SDK raises. Class names are shared by the TypeScript, Go and Python SDKs.
 *
 * These are request failures shared by every product: the HTTP request failed or the server
 * rejected it. Product packages add their own errors (for example `WorkflowFailedError` in
 * `@traceport/workflows`) by extending {@link TraceportError}.
 */

/** HTTP statuses that are safe to retry with the same request and idempotency key. */
const RETRYABLE_STATUSES = new Set([408, 429, 500, 502, 503, 504]);

/**
 * The backend reports an in-progress synchronous replay as
 * `"…; inspect the original run: <uuid>"`. We read the run ID from that message.
 */
const EXISTING_RUN_PATTERN =
  /inspect the original run:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*$/i;

/** Base class for every error thrown by the SDK. */
export class TraceportError extends Error {
  override readonly name: string = "TraceportError";
}

/** Fields the transport passes when it builds an {@link APIError}. */
export interface APIErrorInit {
  /** HTTP status code. */
  status: number;
  /** Human-readable message from the response envelope, or a generic one. */
  message: string;
  /** Stable machine-readable code from the envelope (`errorCode`). Empty when the server sent none. */
  errorCode: string;
  /** Response headers. */
  headers: Headers;
  /** Parsed JSON body, or the raw text when the body was not JSON. */
  body: unknown;
}

/**
 * The server answered with a non-2xx status.
 *
 * Use the subclass (for example {@link NotFoundError}) or `status` to branch, and `errorCode`
 * for the specific reason (for example `"workflow_version_not_found"`).
 */
export class APIError extends TraceportError {
  override readonly name: string = "APIError";
  /** HTTP status code. */
  readonly status: number;
  /** Stable machine-readable code from the response envelope. Empty when the server sent none. */
  readonly errorCode: string;
  /** Response headers. */
  readonly headers: Headers;
  /** Parsed JSON body, or the raw text when the body was not JSON. */
  readonly body: unknown;
  /**
   * Request ID from the `x-request-id` response header, when the server sends one.
   * Include it when you contact support.
   */
  readonly requestId: string | undefined;

  constructor(init: APIErrorInit) {
    super(init.message);
    this.status = init.status;
    this.errorCode = init.errorCode;
    this.headers = init.headers;
    this.body = init.body;
    this.requestId = init.headers.get("x-request-id") ?? undefined;
  }

  /** Whether the SDK treats this status as transient and retries it automatically. */
  get retryable(): boolean {
    return RETRYABLE_STATUSES.has(this.status);
  }

  /** Builds the subclass that matches the HTTP status. */
  static fromResponse(init: APIErrorInit): APIError {
    switch (init.status) {
      case 400:
        return new BadRequestError(init);
      case 401:
        return new AuthenticationError(init);
      case 402:
        return new PaymentRequiredError(init);
      case 403:
        return new PermissionDeniedError(init);
      case 404:
        return new NotFoundError(init);
      case 409:
        return new ConflictError(init);
      case 429:
        return new RateLimitError(init);
      default:
        return init.status >= 500 ? new InternalServerError(init) : new APIError(init);
    }
  }
}

/** 400: the request was invalid, for example an unknown field or a bad query parameter. */
export class BadRequestError extends APIError {
  override readonly name: string = "BadRequestError";
}

/** 401: the API key is missing, unknown, inactive or expired. */
export class AuthenticationError extends APIError {
  override readonly name: string = "AuthenticationError";
}

/** 402: wallet credits are insufficient to start the workflow. */
export class PaymentRequiredError extends APIError {
  override readonly name: string = "PaymentRequiredError";
}

/** 403: the plan does not allow this, or the workflow allowance is exhausted. */
export class PermissionDeniedError extends APIError {
  override readonly name: string = "PermissionDeniedError";
}

/** 404: the version or run does not exist, or belongs to another organization. */
export class NotFoundError extends APIError {
  override readonly name: string = "NotFoundError";
}

/**
 * 409: a conflict. Common causes:
 *  - the idempotency key was already used with a different request body;
 *  - a synchronous request with the same key is still running ({@link existingRunId} is set);
 *  - a validation or revision conflict on the workflow version.
 */
export class ConflictError extends APIError {
  override readonly name: string = "ConflictError";
  /**
   * ID of the run already processing this idempotency key, when the server reports one.
   * Poll it with `workflows.runs.get(existingRunId)` instead of retrying.
   */
  readonly existingRunId: string | undefined;

  constructor(init: APIErrorInit) {
    super(init);
    this.existingRunId = EXISTING_RUN_PATTERN.exec(init.message)?.[1];
  }
}

/** 429: too many requests. Retried automatically, honoring `Retry-After`. */
export class RateLimitError extends APIError {
  override readonly name: string = "RateLimitError";
}

/** 5xx: the server failed or is temporarily unavailable. Retried automatically. */
export class InternalServerError extends APIError {
  override readonly name: string = "InternalServerError";
}

/** The request never produced a response (DNS, TLS, connection reset, …). */
export class APIConnectionError extends TraceportError {
  override readonly name: string = "APIConnectionError";
}

/** The request did not finish within its timeout. */
export class APITimeoutError extends APIConnectionError {
  override readonly name: string = "APITimeoutError";
}

/** The request was cancelled through the caller's `AbortSignal`. Never retried. */
export class RequestAbortedError extends TraceportError {
  override readonly name: string = "RequestAbortedError";
}

/** The server answered with a success status but the body was not a valid Traceport response. */
export class InvalidResponseError extends TraceportError {
  override readonly name: string = "InvalidResponseError";
  /** HTTP status code of the response. */
  readonly status: number;
  /** Parsed JSON body, or the raw text when the body was not JSON. */
  readonly body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}
