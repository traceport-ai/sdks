package traceport

import (
	"net/http"
	"time"

	"github.com/traceport-ai/sdks/go/internal/core"
)

// ClientOption configures a client. Invalid options are reported by NewClient.
type ClientOption = core.ClientOption

// RequestOption configures one logical request, including all its retry attempts.
type RequestOption = core.RequestOption

// WithAPIKey sets the API key instead of reading TRACEPORT_API_KEY.
func WithAPIKey(key string) ClientOption { return core.WithAPIKey(key) }

// WithBaseURL sets the API base URL, including its /v1 prefix.
func WithBaseURL(baseURL string) ClientOption { return core.WithBaseURL(baseURL) }

// WithHTTPClient injects an HTTP client. Its transport must honor request contexts.
// Its own timeout, when set, may shorten SDK timeouts.
func WithHTTPClient(client *http.Client) ClientOption { return core.WithHTTPClient(client) }

// WithTimeout sets the default timeout per attempt, including the response body.
// Execute defaults to at least six minutes; WithRequestTimeout overrides that minimum.
func WithTimeout(timeout time.Duration) ClientOption { return core.WithTimeout(timeout) }

// WithMaxRetries sets the automatic retry limit. The default is two; zero disables retries.
func WithMaxRetries(count int) ClientOption { return core.WithMaxRetries(count) }

// WithDefaultHeaders adds headers to all requests. Authorization and Idempotency-Key are protected.
func WithDefaultHeaders(headers http.Header) ClientOption { return core.WithDefaultHeaders(headers) }

// WithRequestTimeout overrides the timeout per attempt, including synchronous Execute's minimum.
func WithRequestTimeout(timeout time.Duration) RequestOption { return core.WithRequestTimeout(timeout) }

// WithRequestMaxRetries overrides the retry limit for one logical call.
func WithRequestMaxRetries(count int) RequestOption { return core.WithRequestMaxRetries(count) }

// WithHeaders adds per-request headers. Authorization and Idempotency-Key cannot be overridden.
func WithHeaders(headers http.Header) RequestOption { return core.WithHeaders(headers) }

// WithIdempotencyKey sets a mutation key: 1-200 bytes without whitespace/control
// characters. Persist one key per logical operation to retry safely across restarts.
func WithIdempotencyKey(key string) RequestOption { return core.WithIdempotencyKey(key) }
