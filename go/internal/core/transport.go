package core

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"math"
	"math/rand"
	"net"
	"net/http"
	"net/url"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// Request describes one logical API call, including any retry attempts.
type Request struct {
	Method, Path   string
	Query          url.Values
	Body           any
	Mutation       bool
	RetryOnTimeout bool
	MinimumTimeout time.Duration
}

// Response contains the unwrapped envelope data and HTTP metadata.
type Response struct {
	Data    json.RawMessage
	Status  int
	Headers http.Header
}

// Do sends an API request through a client's shared authentication, timeout and retry
// policies. Product packages call it; it is a function in this internal package rather than a
// method so it never appears on the public traceport.Client.
func Do(ctx context.Context, c *Client, request Request, requestOptions ...RequestOption) (Response, error) {
	if c == nil {
		return Response{}, Invalid("client", "must not be nil; create one with traceport.NewClient")
	}
	return c.do(ctx, request, requestOptions...)
}

func (c *Client) do(ctx context.Context, request Request, requestOptions ...RequestOption) (Response, error) {
	options, err := resolveRequestOptions(requestOptions)
	if err != nil {
		return Response{}, err
	}
	if ctx == nil {
		return Response{}, Invalid("context", "must not be nil")
	}
	if err := ctx.Err(); err != nil {
		return Response{}, &RequestAbortedError{Cause: context.Cause(ctx)}
	}
	timeout := c.settings.timeout
	if request.MinimumTimeout > timeout {
		timeout = request.MinimumTimeout
	}
	if options.hasTimeout {
		timeout = options.timeout
	}
	maxRetries := c.settings.maxRetries
	if options.hasMaxRetries {
		maxRetries = options.maxRetries
	}
	var body []byte
	if request.Body != nil {
		var err error
		body, err = json.Marshal(request.Body)
		if err != nil {
			return Response{}, Invalid("input", "must contain JSON-serializable values: "+err.Error())
		}
	}
	headers := make(http.Header)
	headers.Set("Accept", "application/json")
	headers.Set("Authorization", "Bearer "+c.settings.apiKey)
	headers.Set("User-Agent", "traceport-go/"+Version+" "+runtime.Version())
	if body != nil {
		headers.Set("Content-Type", "application/json")
	}
	if request.Mutation {
		key := options.idempotencyKey
		if key == "" {
			var err error
			key, err = randomKey()
			if err != nil {
				return Response{}, err
			}
		}
		headers.Set("Idempotency-Key", key)
	}
	for _, extra := range []http.Header{c.settings.headers, options.headers} {
		for key, values := range extra {
			if strings.EqualFold(key, "Authorization") || strings.EqualFold(key, "Idempotency-Key") {
				continue
			}
			headers.Del(key)
			for _, value := range values {
				headers.Add(key, value)
			}
		}
	}
	endpoint := c.settings.baseURL + request.Path
	if len(request.Query) > 0 {
		endpoint += "?" + request.Query.Encode()
	}
	for attempt := 0; ; attempt++ {
		response, raw, err := c.sendAttempt(ctx, request.Method, endpoint, body, headers, timeout)
		if err != nil {
			var connection *APIConnectionError
			var timedOut *APITimeoutError
			retryable := errors.As(err, &connection) && (!errors.As(err, &timedOut) || request.RetryOnTimeout)
			if attempt < maxRetries && retryable {
				if err := Sleep(ctx, backoff(attempt)); err != nil {
					return Response{}, err
				}
				continue
			}
			return Response{}, err
		}
		parsed := ParseBody(raw)
		if response.StatusCode >= 200 && response.StatusCode < 300 {
			var envelope map[string]json.RawMessage
			if json.Unmarshal(raw, &envelope) != nil || envelope["data"] == nil {
				return Response{}, &InvalidResponseError{Message: "response is not a Traceport API envelope", StatusCode: response.StatusCode, Body: parsed}
			}
			var message string
			_ = json.Unmarshal(envelope["error"], &message)
			if strings.TrimSpace(message) != "" {
				return Response{}, &InvalidResponseError{Message: "success response reported an error: " + message, StatusCode: response.StatusCode, Body: parsed}
			}
			return Response{Data: envelope["data"], Status: response.StatusCode, Headers: response.Header.Clone()}, nil
		}
		failure := statusError(response.StatusCode, response.Header, parsed)
		if attempt < maxRetries && retryableStatus(response.StatusCode) {
			if err := Sleep(ctx, retryDelay(response.Header, attempt)); err != nil {
				return Response{}, err
			}
			continue
		}
		return Response{}, failure
	}
}

func (c *Client) sendAttempt(ctx context.Context, method, endpoint string, body []byte, headers http.Header, timeout time.Duration) (*http.Response, []byte, error) {
	attemptCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(attemptCtx, method, endpoint, bytes.NewReader(body))
	if err != nil {
		return nil, nil, Invalid("request", err.Error())
	}
	request.Header = headers.Clone()
	response, err := c.settings.httpClient.Do(request)
	if err == nil {
		defer response.Body.Close()
		var raw []byte
		raw, err = io.ReadAll(response.Body)
		if err == nil && attemptCtx.Err() == nil {
			return response, raw, nil
		}
		if err == nil {
			err = attemptCtx.Err()
		}
	}
	if ctx.Err() != nil {
		return nil, nil, &RequestAbortedError{Cause: context.Cause(ctx)}
	}
	connection := &APIConnectionError{Cause: err}
	var networkError net.Error
	if errors.Is(err, context.DeadlineExceeded) || attemptCtx.Err() == context.DeadlineExceeded || (errors.As(err, &networkError) && networkError.Timeout()) {
		return nil, nil, &APITimeoutError{APIConnectionError: connection, Timeout: timeout}
	}
	return nil, nil, connection
}

// ParseBody decodes JSON when possible, otherwise preserving the original body text.
func ParseBody(raw []byte) any {
	if len(bytes.TrimSpace(raw)) == 0 {
		return nil
	}
	var value any
	if json.Unmarshal(raw, &value) == nil {
		return value
	}
	return string(raw)
}

// Sleep waits for a retry or poll interval while honoring cancellation.
func Sleep(ctx context.Context, delay time.Duration) error {
	if ctx.Err() != nil {
		return &RequestAbortedError{Cause: context.Cause(ctx)}
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return &RequestAbortedError{Cause: context.Cause(ctx)}
	case <-timer.C:
		if ctx.Err() != nil {
			return &RequestAbortedError{Cause: context.Cause(ctx)}
		}
		return nil
	}
}

func backoff(attempt int) time.Duration {
	base := 8 * time.Second
	if attempt < 4 {
		base = 500 * time.Millisecond * time.Duration(1<<attempt)
	}
	return time.Duration(float64(base) * (1 - rand.Float64()*0.25))
}

func retryDelay(headers http.Header, attempt int) time.Duration {
	value := headers.Get("Retry-After")
	if value != "" {
		var seconds float64
		if number, err := strconv.ParseFloat(value, 64); err == nil {
			seconds = number
		} else if date, err := http.ParseTime(value); err == nil {
			seconds = time.Until(date).Seconds()
		} else {
			return backoff(attempt)
		}
		if math.IsNaN(seconds) || math.IsInf(seconds, 0) {
			return backoff(attempt)
		}
		if seconds >= 60 {
			return time.Minute
		}
		if seconds >= 0 {
			return time.Duration(seconds * float64(time.Second))
		}
	}
	return backoff(attempt)
}
