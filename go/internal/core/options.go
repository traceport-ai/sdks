package core

import (
	"net/http"
	"time"
)

// ClientOption configures a client. Invalid options are reported by NewClient.
type ClientOption func(*clientSettings) error

// RequestOption configures one logical request, including all its retry attempts.
type RequestOption func(*requestSettings) error

type clientSettings struct {
	apiKey     string
	baseURL    string
	timeout    time.Duration
	maxRetries int
	httpClient *http.Client
	headers    http.Header
}

type requestSettings struct {
	timeout        time.Duration
	hasTimeout     bool
	maxRetries     int
	hasMaxRetries  bool
	idempotencyKey string
	headers        http.Header
}

// WithAPIKey sets the API key instead of reading TRACEPORT_API_KEY.
func WithAPIKey(key string) ClientOption {
	return func(c *clientSettings) error { c.apiKey = key; return nil }
}

// WithBaseURL sets the API base URL, including its /v1 prefix.
func WithBaseURL(baseURL string) ClientOption {
	return func(c *clientSettings) error { c.baseURL = baseURL; return nil }
}

// WithHTTPClient injects an HTTP client. Its transport must honor request contexts.
// An HTTP client timeout, when set, also applies and may shorten SDK timeouts.
func WithHTTPClient(client *http.Client) ClientOption {
	return func(c *clientSettings) error {
		if client == nil {
			return Invalid("httpClient", "must not be nil")
		}
		c.httpClient = client
		return nil
	}
}

// WithTimeout sets the default timeout per attempt, including the response body.
// Execute defaults to at least six minutes; WithRequestTimeout overrides that minimum.
func WithTimeout(timeout time.Duration) ClientOption {
	return func(c *clientSettings) error {
		if err := ValidateDuration(timeout, "timeout"); err != nil {
			return err
		}
		c.timeout = timeout
		return nil
	}
}

// WithMaxRetries sets the automatic retry limit. The default is two; zero disables retries.
func WithMaxRetries(count int) ClientOption {
	return func(c *clientSettings) error {
		if err := validateRetries(count); err != nil {
			return err
		}
		c.maxRetries = count
		return nil
	}
}

// WithDefaultHeaders adds headers to all requests. Authorization and Idempotency-Key are protected.
func WithDefaultHeaders(headers http.Header) ClientOption {
	return func(c *clientSettings) error { c.headers = headers.Clone(); return nil }
}

// WithRequestTimeout overrides the timeout per attempt, including synchronous Execute's minimum.
func WithRequestTimeout(timeout time.Duration) RequestOption {
	return func(r *requestSettings) error {
		if err := ValidateDuration(timeout, "requestTimeout"); err != nil {
			return err
		}
		r.timeout, r.hasTimeout = timeout, true
		return nil
	}
}

// WithRequestMaxRetries overrides the retry limit for one logical call.
func WithRequestMaxRetries(count int) RequestOption {
	return func(r *requestSettings) error {
		if err := validateRetries(count); err != nil {
			return err
		}
		r.maxRetries, r.hasMaxRetries = count, true
		return nil
	}
}

// WithHeaders adds per-request headers. Authorization and Idempotency-Key cannot be overridden.
func WithHeaders(headers http.Header) RequestOption {
	return func(r *requestSettings) error { r.headers = headers.Clone(); return nil }
}

// WithIdempotencyKey sets the key for Execute or Runs.Start. Persist one key per
// logical operation to retry safely across restarts. At most 200 UTF-8 bytes,
// without whitespace or control characters. A key is generated when omitted.
func WithIdempotencyKey(key string) RequestOption {
	return func(r *requestSettings) error {
		if err := validateKey(key); err != nil {
			return err
		}
		r.idempotencyKey = key
		return nil
	}
}

func resolveRequestOptions(options []RequestOption) (requestSettings, error) {
	var settings requestSettings
	for _, option := range options {
		if option == nil {
			return settings, Invalid("requestOption", "must not be nil")
		}
		if err := option(&settings); err != nil {
			return settings, err
		}
	}
	return settings, nil
}

// ValidateRequestOptions validates options without making an HTTP request.
func ValidateRequestOptions(options ...RequestOption) error {
	_, err := resolveRequestOptions(options)
	return err
}
