package core

import (
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

const (
	// Version is the SDK's pre-release version.
	Version = "0.1.0"
	// DefaultBaseURL includes the public API version prefix.
	DefaultBaseURL = "https://api.traceport.ai/v1"
)

// Client owns shared HTTP configuration and transport for every product package. It is
// exposed publicly as traceport.Client and passed to products such as workflows.New.
type Client struct {
	settings clientSettings
}

// NewClient reads TRACEPORT_API_KEY and TRACEPORT_BASE_URL unless overridden.
// No network requests are made during construction.
func NewClient(options ...ClientOption) (*Client, error) {
	baseURL := strings.TrimSpace(os.Getenv("TRACEPORT_BASE_URL"))
	if baseURL == "" {
		baseURL = DefaultBaseURL
	}
	settings := clientSettings{
		apiKey:     strings.TrimSpace(os.Getenv("TRACEPORT_API_KEY")),
		baseURL:    baseURL,
		timeout:    time.Minute,
		maxRetries: 2,
		httpClient: &http.Client{},
	}
	for _, option := range options {
		if option == nil {
			return nil, Invalid("clientOption", "must not be nil")
		}
		if err := option(&settings); err != nil {
			return nil, err
		}
	}
	settings.apiKey = strings.TrimSpace(settings.apiKey)
	if settings.apiKey == "" {
		return nil, Invalid("apiKey", "pass WithAPIKey or set TRACEPORT_API_KEY")
	}
	if strings.ContainsAny(settings.apiKey, "\r\n") {
		return nil, Invalid("apiKey", "must not contain newlines")
	}
	settings.baseURL = strings.TrimRight(settings.baseURL, "/")
	parsed, err := url.Parse(settings.baseURL)
	if err != nil || parsed.Host == "" || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.RawQuery != "" || parsed.Fragment != "" || parsed.User != nil {
		return nil, Invalid("baseURL", "must be an absolute HTTP(S) URL without credentials, query or fragment")
	}
	client := &Client{settings: settings}
	return client, nil
}

// WithOptions returns a new client with this client's API key, base URL and HTTP client (and
// therefore its connection pool), and with other settings changed. Use it to give one product
// different timeouts, retries or headers without configuring a second client.
//
// Only WithTimeout, WithMaxRetries and WithDefaultHeaders are accepted. Default headers are
// merged over this client's. Options that would change the API key, base URL or HTTP client
// return a ValidationError, because a derived client must talk to the same API as the same
// organization. The original client is not modified.
func (c *Client) WithOptions(options ...ClientOption) (*Client, error) {
	if c == nil {
		return nil, Invalid("client", "must not be nil")
	}
	derived := c.settings
	// Start without headers so we can tell whether an option supplied new ones.
	derived.headers = nil
	for _, option := range options {
		if option == nil {
			return nil, Invalid("clientOption", "must not be nil")
		}
		if err := option(&derived); err != nil {
			return nil, err
		}
	}
	if derived.apiKey != c.settings.apiKey || derived.baseURL != c.settings.baseURL || derived.httpClient != c.settings.httpClient {
		return nil, Invalid("clientOption", "WithOptions accepts only WithTimeout, WithMaxRetries and WithDefaultHeaders")
	}
	merged := c.settings.headers.Clone()
	if merged == nil {
		merged = http.Header{}
	}
	for name, values := range derived.headers {
		merged[name] = append([]string(nil), values...)
	}
	derived.headers = merged
	return &Client{settings: derived}, nil
}
