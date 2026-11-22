package traceport

import "github.com/traceport-ai/sdks/go/internal/core"

// TraceportError is implemented by SDK errors.
type TraceportError = core.TraceportError

// ValidationError reports invalid arguments before HTTP is sent.
type ValidationError = core.ValidationError

// APIError describes an HTTP failure. Specific status errors unwrap to this type.
type APIError = core.APIError

// BadRequestError is HTTP 400: invalid request or query parameters.
type BadRequestError = core.BadRequestError

// AuthenticationError is HTTP 401: missing, unknown, inactive or expired key.
type AuthenticationError = core.AuthenticationError

// PaymentRequiredError is HTTP 402: insufficient wallet credits.
type PaymentRequiredError = core.PaymentRequiredError

// PermissionDeniedError is HTTP 403: plan or allowance restrictions.
type PermissionDeniedError = core.PermissionDeniedError

// NotFoundError is HTTP 404: missing or foreign-organization resource.
type NotFoundError = core.NotFoundError

// ConflictError is HTTP 409: idempotency, in-progress replay or version conflict.
type ConflictError = core.ConflictError

// RateLimitError is HTTP 429 and is retried within the configured limit.
type RateLimitError = core.RateLimitError

// InternalServerError is HTTP 5xx; Retryable identifies the transient subset.
type InternalServerError = core.InternalServerError

// APIConnectionError includes connection failures while reading response bodies.
type APIConnectionError = core.APIConnectionError

// APITimeoutError reports a request timeout and unwraps to APIConnectionError.
type APITimeoutError = core.APITimeoutError

// RequestAbortedError reports cancellation or deadline expiry of the caller's context.
type RequestAbortedError = core.RequestAbortedError

// InvalidResponseError reports a successful HTTP response with an invalid body.
type InvalidResponseError = core.InvalidResponseError
