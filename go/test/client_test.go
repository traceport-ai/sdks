package test

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	traceport "github.com/traceport-ai/sdks/go"
	"github.com/traceport-ai/sdks/go/workflows"
)

// One client serves every product: products built from the same client, or from a client
// derived with WithOptions, share its credentials and HTTP client.
func TestProductsShareOneClient(t *testing.T) {
	var calls atomic.Int32
	httpClient := &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
		calls.Add(1)
		if request.Header.Get("Authorization") != "Bearer test-key" {
			t.Errorf("authorization %q", request.Header.Get("Authorization"))
		}
		return response(200, runData("running")), nil
	})}
	client, err := traceport.NewClient(traceport.WithAPIKey("test-key"), traceport.WithBaseURL("https://api.test/v1"), traceport.WithHTTPClient(httpClient))
	if err != nil {
		t.Fatal(err)
	}
	derived, err := client.WithOptions(traceport.WithTimeout(5 * time.Second))
	if err != nil {
		t.Fatal(err)
	}
	for _, wf := range []*workflows.Service{workflows.New(client), workflows.New(client), workflows.New(derived)} {
		if _, err := wf.Runs.Get(context.Background(), runID); err != nil {
			t.Fatal(err)
		}
	}
	if calls.Load() != 3 {
		t.Fatalf("calls = %d, want 3 through the one injected HTTP client", calls.Load())
	}
}

func TestWithOptionsMergesHeadersAndKeepsOriginal(t *testing.T) {
	var seen []http.Header
	client := clientFor(t, func(request *http.Request) (*http.Response, error) {
		seen = append(seen, request.Header.Clone())
		return response(200, runData("running")), nil
	}, traceport.WithDefaultHeaders(http.Header{"X-Team": {"a"}, "X-Keep": {"1"}}))

	derived, err := client.WithOptions(traceport.WithDefaultHeaders(http.Header{"X-Team": {"b"}}), traceport.WithMaxRetries(3))
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	if _, err := workflows.New(client).Runs.Get(ctx, runID); err != nil {
		t.Fatal(err)
	}
	if _, err := workflows.New(derived).Runs.Get(ctx, runID); err != nil {
		t.Fatal(err)
	}
	if got := seen[0].Get("X-Team"); got != "a" {
		t.Errorf("original X-Team = %q, want a", got)
	}
	if got := seen[1].Get("X-Team"); got != "b" {
		t.Errorf("derived X-Team = %q, want b", got)
	}
	if got := seen[1].Get("X-Keep"); got != "1" {
		t.Errorf("derived X-Keep = %q, want merged 1", got)
	}
	if got := seen[1].Get("Authorization"); got != "Bearer test-key" {
		t.Errorf("derived Authorization = %q", got)
	}
}

func TestWithOptionsAppliesRetriesOnlyToDerivedClient(t *testing.T) {
	var calls atomic.Int32
	client := clientFor(t, func(*http.Request) (*http.Response, error) {
		calls.Add(1)
		return errorResponse(503, "unavailable", "workflow_executor_unavailable", "0"), nil
	})
	ctx := context.Background()
	_, _ = workflows.New(client).Runs.Get(ctx, runID)
	if calls.Load() != 1 {
		t.Fatalf("original made %d attempts, want 1", calls.Load())
	}
	derived, err := client.WithOptions(traceport.WithMaxRetries(1))
	if err != nil {
		t.Fatal(err)
	}
	_, _ = workflows.New(derived).Runs.Get(ctx, runID)
	if calls.Load() != 3 {
		t.Fatalf("derived made %d attempts, want 2", calls.Load()-1)
	}
}

// A derived client must keep the same credentials, API and connections.
func TestWithOptionsRejectsIdentityChanges(t *testing.T) {
	client := clientFor(t, func(*http.Request) (*http.Response, error) { return response(200, runData("running")), nil })
	for name, option := range map[string]traceport.ClientOption{
		"api key":     traceport.WithAPIKey("other"),
		"base URL":    traceport.WithBaseURL("https://other.test/v1"),
		"http client": traceport.WithHTTPClient(&http.Client{}),
		"nil option":  nil,
	} {
		_, err := client.WithOptions(option)
		var validation *traceport.ValidationError
		if !errors.As(err, &validation) {
			t.Errorf("%s: err = %v, want ValidationError", name, err)
		}
	}
	if _, err := client.WithOptions(traceport.WithTimeout(-time.Second)); err == nil {
		t.Error("invalid timeout accepted")
	}
}

func TestNilClientIsAValidationError(t *testing.T) {
	_, err := workflows.New(nil).Runs.Get(context.Background(), runID)
	var validation *traceport.ValidationError
	if !errors.As(err, &validation) {
		t.Fatalf("err = %v, want ValidationError", err)
	}
	var nilClient *traceport.Client
	if _, err := nilClient.WithOptions(); !errors.As(err, &validation) {
		t.Fatalf("WithOptions on nil: err = %v, want ValidationError", err)
	}
}

// errorResponse is an error envelope with an optional Retry-After header.
func errorResponse(status int, message, code, retryAfter string) *http.Response {
	result := response(status, nil)
	body, err := json.Marshal(map[string]any{"data": nil, "error": message, "status": status, "errorCode": code})
	if err != nil {
		panic(err)
	}
	result.Body = io.NopCloser(strings.NewReader(string(body)))
	if retryAfter != "" {
		result.Header.Set("Retry-After", retryAfter)
	}
	return result
}
