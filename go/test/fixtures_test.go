package test

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"

	traceport "github.com/traceport-ai/sdks/go"
	"github.com/traceport-ai/sdks/go/workflows"
)

const versionID = "00000000-0000-4000-8000-000000000001"
const runID = "00000000-0000-4000-8000-000000000002"

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) { return fn(request) }

func clientFor(t *testing.T, transport roundTripFunc, options ...traceport.ClientOption) *traceport.Client {
	t.Helper()
	base := []traceport.ClientOption{traceport.WithAPIKey("test-key"), traceport.WithBaseURL("https://api.test/v1"), traceport.WithMaxRetries(0), traceport.WithHTTPClient(&http.Client{Transport: transport})}
	client, err := traceport.NewClient(append(base, options...)...)
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func response(status int, data any) *http.Response {
	body, err := json.Marshal(map[string]any{"data": data, "error": "", "status": status, "errorCode": ""})
	if err != nil {
		panic(err)
	}
	return &http.Response{StatusCode: status, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(string(body)))}
}

func runData(status string) map[string]any {
	return map[string]any{"id": runID, "configVersionID": versionID, "revision": 1, "status": status, "mode": "production", "source": "api_async", "createdAt": "2026-11-12T10:00:00Z"}
}

func workflowData() map[string]any {
	return map[string]any{"data": map[string]any{"final": map[string]any{"ok": true}}, "error": "", "steps": []any{}}
}

type outcome struct {
	Status    string `json:"status"`
	Output    any    `json:"output"`
	Error     string `json:"error"`
	StepCount *int   `json:"stepCount"`
}

type fixture struct {
	Name      string `json:"name"`
	Operation string `json:"operation"`
	Request   struct {
		Method  string            `json:"method"`
		Path    string            `json:"path"`
		Headers map[string]string `json:"headers"`
		Body    json.RawMessage   `json:"body"`
	} `json:"request"`
	Response struct {
		Status  int               `json:"status"`
		Headers map[string]string `json:"headers"`
		Body    json.RawMessage   `json:"body"`
	} `json:"response"`
	Expect struct {
		Kind     string         `json:"kind"`
		Resource map[string]any `json:"resource"`
		Outcome  *outcome       `json:"outcome"`
		Error    struct {
			Class         string `json:"class"`
			Status        int    `json:"status"`
			ErrorCode     string `json:"errorCode"`
			Retryable     bool   `json:"retryable"`
			ExistingRunID string `json:"existingRunId"`
		} `json:"error"`
	} `json:"expect"`
}

func TestSharedFixtures(t *testing.T) {
	count := 0
	err := filepath.WalkDir("../../fixtures", func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || filepath.Ext(path) != ".json" {
			return nil
		}
		count++
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		var fixture fixture
		if err := json.Unmarshal(data, &fixture); err != nil {
			return err
		}
		t.Run(fixture.Name, func(t *testing.T) { replayFixture(t, fixture) })
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if count == 0 {
		t.Fatal("no shared fixtures replayed")
	}
}

func replayFixture(t *testing.T, fixture fixture) {
	t.Helper()
	calls := 0
	client := clientFor(t, func(request *http.Request) (*http.Response, error) {
		calls++
		if request.Method != fixture.Request.Method {
			t.Errorf("method %s", request.Method)
		}
		expected, _ := url.Parse("https://api.test" + fixture.Request.Path)
		if request.URL.Path != expected.Path || !reflect.DeepEqual(request.URL.Query(), expected.Query()) {
			t.Errorf("URL %s, expected %s", request.URL, expected)
		}
		var body []byte
		if request.Body != nil {
			body, _ = io.ReadAll(request.Body)
		}
		assertJSONEqual(t, body, fixture.Request.Body)
		if request.Header.Get("Authorization") != "Bearer test-key" {
			t.Error("missing credentials")
		}
		for name, value := range fixture.Request.Headers {
			if request.Header.Get(name) != value {
				t.Errorf("header %s", name)
			}
		}
		headers := make(http.Header)
		for name, value := range fixture.Response.Headers {
			headers.Set(name, value)
		}
		return &http.Response{StatusCode: fixture.Response.Status, Header: headers, Body: io.NopCloser(strings.NewReader(string(fixture.Response.Body)))}, nil
	})
	var params struct {
		VersionID string         `json:"configVersionID"`
		Input     map[string]any `json:"additional"`
	}
	if len(fixture.Request.Body) > 0 {
		if err := json.Unmarshal(fixture.Request.Body, &params); err != nil {
			t.Fatal(err)
		}
	}
	start := workflows.StartParams{VersionID: params.VersionID, Input: params.Input}
	var options []traceport.RequestOption
	if key := fixture.Request.Headers["Idempotency-Key"]; key != "" {
		options = append(options, traceport.WithIdempotencyKey(key))
	}
	var result *workflows.Result
	var run *workflows.Run
	var page *workflows.RunPage
	var err error
	parsed, _ := url.Parse(fixture.Request.Path)
	switch fixture.Operation {
	case "executeWorkflow":
		result, err = workflows.New(client).Execute(context.Background(), start, options...)
	case "startWorkflowRun":
		run, err = workflows.New(client).Runs.Start(context.Background(), start, options...)
	case "getWorkflowRun":
		run, err = workflows.New(client).Runs.Get(context.Background(), filepath.Base(parsed.Path))
	case "listWorkflowRuns":
		query := parsed.Query()
		params := workflows.ListRunsParams{VersionID: query.Get("configVersionID"), Status: workflows.RunStatus(query.Get("status"))}
		if query.Has("limit") {
			value, _ := strconv.Atoi(query.Get("limit"))
			params.Limit = &value
		}
		if query.Has("offset") {
			value, _ := strconv.Atoi(query.Get("offset"))
			params.Offset = &value
		}
		page, err = workflows.New(client).Runs.List(context.Background(), params)
	default:
		t.Fatalf("unhandled operation %s", fixture.Operation)
	}
	if calls != 1 {
		t.Fatalf("sent %d requests", calls)
	}
	if fixture.Expect.Kind == "error" {
		if err == nil {
			t.Fatal("expected error")
		}
		if name := reflect.TypeOf(err).Elem().Name(); name != fixture.Expect.Error.Class {
			t.Errorf("error %s, expected %s", name, fixture.Expect.Error.Class)
		}
		var apiError *traceport.APIError
		if !errors.As(err, &apiError) {
			t.Fatalf("missing APIError: %v", err)
		}
		if apiError.StatusCode != fixture.Expect.Error.Status || apiError.ErrorCode != fixture.Expect.Error.ErrorCode || apiError.Retryable != fixture.Expect.Error.Retryable {
			t.Errorf("APIError: %+v", apiError)
		}
		if fixture.Expect.Error.ExistingRunID != "" {
			var conflict *traceport.ConflictError
			if !errors.As(err, &conflict) || conflict.ExistingRunID != fixture.Expect.Error.ExistingRunID {
				t.Errorf("existing run ID: %v", err)
			}
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	if fixture.Expect.Outcome != nil {
		if run != nil {
			result = run.Result
		}
		assertOutcome(t, result, fixture.Expect.Outcome)
	}
	if page != nil {
		if len(page.Items) != int(fixture.Expect.Resource["itemCount"].(float64)) || page.Limit != int(fixture.Expect.Resource["limit"].(float64)) || page.Offset != int(fixture.Expect.Resource["offset"].(float64)) {
			t.Errorf("page: %+v", page)
		}
		for _, item := range page.Items {
			if item.Output != nil || item.Result != nil {
				t.Error("summary contains output")
			}
		}
	}
	if run != nil {
		encoded, _ := json.Marshal(run)
		var fields map[string]any
		_ = json.Unmarshal(encoded, &fields)
		for key, value := range fixture.Expect.Resource {
			if !reflect.DeepEqual(fields[key], value) {
				t.Errorf("resource %s: %v != %v", key, fields[key], value)
			}
		}
	}
}

func assertOutcome(t *testing.T, result *workflows.Result, expected *outcome) {
	t.Helper()
	if result == nil {
		t.Fatal("missing interpreted result")
	}
	if string(result.Status) != expected.Status || result.Error != expected.Error || !reflect.DeepEqual(result.Output, expected.Output) {
		t.Errorf("outcome: %+v, expected %+v", result, expected)
	}
	if expected.StepCount != nil && len(result.Steps) != *expected.StepCount {
		t.Errorf("step count %d", len(result.Steps))
	}
}

func assertJSONEqual(t *testing.T, actual, expected []byte) {
	t.Helper()
	var left, right any
	if len(actual) > 0 {
		if err := json.Unmarshal(actual, &left); err != nil {
			t.Fatal(err)
		}
	}
	if len(expected) > 0 {
		if err := json.Unmarshal(expected, &right); err != nil {
			t.Fatal(err)
		}
	}
	if !reflect.DeepEqual(left, right) {
		t.Errorf("JSON %s != %s", actual, expected)
	}
}
