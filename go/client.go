package traceport

import "github.com/traceport-ai/sdks/go/internal/core"

const (
	// Version is the SDK release version, sent in the User-Agent header.
	Version = core.Version
	// DefaultBaseURL includes the public API version prefix.
	DefaultBaseURL = core.DefaultBaseURL
)

// Client is the shared Traceport client. Create one with NewClient and pass it to every
// product package you use, for example workflows.New(client). It holds the API key, base URL,
// HTTP client, timeouts and retry policy, so products need no configuration of their own.
//
// A Client is safe for concurrent use. Use Client.WithOptions to derive a client with
// different timeouts, retries or default headers that keeps the same credentials and
// connection pool.
type Client = core.Client

// NewClient reads TRACEPORT_API_KEY and TRACEPORT_BASE_URL unless overridden.
// No network requests are made during construction.
func NewClient(options ...ClientOption) (*Client, error) {
	return core.NewClient(options...)
}
