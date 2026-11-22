package core

import (
	"fmt"
	"net/http"
	"regexp"
	"time"
)

// TraceportError is implemented by SDK errors. ValidationError reports local misuse.
// Standard context errors remain available through errors.Is on Unwrap chains.
type TraceportError interface {
	error
	traceportError()
}

// ValidationError reports invalid arguments before HTTP is sent.
type ValidationError struct{ Field, Message string }

func (e *ValidationError) Error() string { return "traceport: " + e.Field + " " + e.Message }
func (*ValidationError) traceportError() {}

// APIError describes an HTTP failure. Specific status errors unwrap to this type,
// so errors.As(err, &apiError) works for all API status errors.
type APIError struct {
	StatusCode int
	Message    string
	ErrorCode  string
	Headers    http.Header
	Body       any
	RequestID  string
	Retryable  bool
}

func (e *APIError) Error() string { return e.Message }
func (*APIError) traceportError() {}

// BadRequestError is HTTP 400: invalid request or query parameters.
type BadRequestError struct{ *APIError }

func (e *BadRequestError) Unwrap() error { return e.APIError }

// AuthenticationError is HTTP 401: missing, unknown, inactive or expired key.
type AuthenticationError struct{ *APIError }

func (e *AuthenticationError) Unwrap() error { return e.APIError }

// PaymentRequiredError is HTTP 402: insufficient wallet credits.
type PaymentRequiredError struct{ *APIError }

func (e *PaymentRequiredError) Unwrap() error { return e.APIError }

// PermissionDeniedError is HTTP 403: plan or allowance restrictions.
type PermissionDeniedError struct{ *APIError }

func (e *PermissionDeniedError) Unwrap() error { return e.APIError }

// NotFoundError is HTTP 404: the resource is missing or belongs to another organization.
type NotFoundError struct{ *APIError }

func (e *NotFoundError) Unwrap() error { return e.APIError }

// ConflictError is HTTP 409: idempotency conflict, in-progress replay or version conflict.
type ConflictError struct {
	*APIError
	ExistingRunID string
}

func (e *ConflictError) Unwrap() error { return e.APIError }

// RateLimitError is HTTP 429 and is retried within the configured limit.
type RateLimitError struct{ *APIError }

func (e *RateLimitError) Unwrap() error { return e.APIError }

// InternalServerError is HTTP 5xx; Retryable identifies the transient subset.
type InternalServerError struct{ *APIError }

func (e *InternalServerError) Unwrap() error { return e.APIError }

// APIConnectionError includes connection failures while reading response bodies.
type APIConnectionError struct{ Cause error }

func (e *APIConnectionError) Error() string {
	if e.Cause == nil {
		return "traceport: could not connect to the API"
	}
	return "traceport: could not connect to the API: " + e.Cause.Error()
}
func (e *APIConnectionError) Unwrap() error { return e.Cause }
func (*APIConnectionError) traceportError() {}

// APITimeoutError reports a request timeout; it unwraps to APIConnectionError.
type APITimeoutError struct {
	*APIConnectionError
	Timeout time.Duration
}

func (e *APITimeoutError) Error() string {
	return fmt.Sprintf("traceport: request timed out (timeout %s)", e.Timeout)
}
func (e *APITimeoutError) Unwrap() error { return e.APIConnectionError }

// RequestAbortedError reports cancellation or deadline expiry of the caller's context.
type RequestAbortedError struct{ Cause error }

func (e *RequestAbortedError) Error() string {
	if e.Cause == nil {
		return "traceport: request was aborted"
	}
	return "traceport: request was aborted: " + e.Cause.Error()
}
func (e *RequestAbortedError) Unwrap() error { return e.Cause }
func (*RequestAbortedError) traceportError() {}

// InvalidResponseError reports a successful HTTP response with an invalid envelope or resource.
type InvalidResponseError struct {
	Message    string
	StatusCode int
	Body       any
}

func (e *InvalidResponseError) Error() string { return "traceport: " + e.Message }
func (*InvalidResponseError) traceportError() {}

var existingRunPattern = regexp.MustCompile(`(?i)inspect the original run:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*$`)

func retryableStatus(status int) bool {
	switch status {
	case 408, 429, 500, 502, 503, 504:
		return true
	}
	return false
}

func statusError(status int, headers http.Header, body any) error {
	message := fmt.Sprintf("request failed with HTTP %d", status)
	code := ""
	if envelope, ok := body.(map[string]any); ok {
		if value, ok := envelope["error"].(string); ok && value != "" {
			message = value
		}
		code, _ = envelope["errorCode"].(string)
	}
	base := &APIError{StatusCode: status, Message: message, ErrorCode: code, Headers: headers.Clone(), Body: body, RequestID: headers.Get("X-Request-Id"), Retryable: retryableStatus(status)}
	switch status {
	case 400:
		return &BadRequestError{base}
	case 401:
		return &AuthenticationError{base}
	case 402:
		return &PaymentRequiredError{base}
	case 403:
		return &PermissionDeniedError{base}
	case 404:
		return &NotFoundError{base}
	case 409:
		conflict := &ConflictError{APIError: base}
		if match := existingRunPattern.FindStringSubmatch(message); len(match) > 1 {
			conflict.ExistingRunID = match[1]
		}
		return conflict
	case 429:
		return &RateLimitError{base}
	default:
		if status >= 500 {
			return &InternalServerError{base}
		}
		return base
	}
}

// ErrorMarker lets feature errors implement the shared SDK error interface.
type ErrorMarker struct{}

func (ErrorMarker) traceportError() {}
