package test

import (
	"context"
	"errors"
	"io"
	"net/http"
	"reflect"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	traceport "github.com/traceport-ai/sdks/go"
	"github.com/traceport-ai/sdks/go/workflows"
)

func TestClientConfiguration(t *testing.T) {
	t.Setenv("TRACEPORT_API_KEY", "  env-key  ")
	t.Setenv("TRACEPORT_BASE_URL", "https://env.test/v1/")
	client, err := traceport.NewClient(traceport.WithHTTPClient(&http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
		if request.URL.String() != "https://env.test/v1/workflow/runs/"+runID || request.Header.Get("Authorization") != "Bearer env-key" {
			t.Errorf("request %s %v", request.URL, request.Header)
		}
		return response(200, runData("running")), nil
	})}))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := workflows.New(client).Runs.Get(context.Background(), runID); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TRACEPORT_API_KEY", "")
	if _, err := traceport.NewClient(); err == nil {
		t.Fatal("missing key accepted")
	}
}

func TestInvalidClientOptions(t *testing.T) {
	for name, option := range map[string]traceport.ClientOption{
		"timeout zero": traceport.WithTimeout(0), "timeout negative": traceport.WithTimeout(-1),
		"retries": traceport.WithMaxRetries(-1), "httpClient": traceport.WithHTTPClient(nil),
		"URL relative": traceport.WithBaseURL("/v1"), "URL scheme": traceport.WithBaseURL("ftp://api.test/v1"),
		"URL query": traceport.WithBaseURL("https://api.test/v1?x=1"), "URL fragment": traceport.WithBaseURL("https://api.test/v1#x"),
		"URL user": traceport.WithBaseURL("https://user:pass@api.test/v1"), "nil": nil,
	} {
		t.Run(name, func(t *testing.T) {
			_, err := traceport.NewClient(traceport.WithAPIKey("key"), option)
			var validation *traceport.ValidationError
			if !errors.As(err, &validation) {
				t.Fatalf("invalid option accepted: %v", err)
			}
		})
	}
}

func TestInvalidRequestOptionsBeforeHTTP(t *testing.T) {
	client := clientFor(t, func(*http.Request) (*http.Response, error) { t.Fatal("unexpected HTTP"); return nil, nil })
	for name, option := range map[string]traceport.RequestOption{
		"timeout zero": traceport.WithRequestTimeout(0), "timeout negative": traceport.WithRequestTimeout(-1),
		"retries": traceport.WithRequestMaxRetries(-1), "empty key": traceport.WithIdempotencyKey(""),
		"space key": traceport.WithIdempotencyKey("has space"), "control key": traceport.WithIdempotencyKey("tab\there"),
		"long key": traceport.WithIdempotencyKey(strings.Repeat("x", 201)), "nil": nil,
	} {
		t.Run(name, func(t *testing.T) {
			_, err := workflows.New(client).Execute(context.Background(), workflows.StartParams{VersionID: versionID}, option)
			var validation *traceport.ValidationError
			if !errors.As(err, &validation) {
				t.Fatalf("invalid option accepted: %v", err)
			}
		})
	}
	if _, err := workflows.New(client).Runs.Get(nil, runID); err == nil {
		t.Fatal("nil context accepted")
	}
	if _, err := workflows.New(client).Runs.Get(context.Background(), " "); err == nil {
		t.Fatal("empty run ID accepted")
	}
	if _, err := workflows.New(client).Execute(context.Background(), workflows.StartParams{}); err == nil {
		t.Fatal("empty version ID accepted")
	}
	if _, err := workflows.New(client).Execute(context.Background(), workflows.StartParams{VersionID: versionID, Input: map[string]any{"bad": make(chan int)}}); err == nil {
		t.Fatal("non-JSON input accepted")
	}
}

func TestHeadersAndIdempotency(t *testing.T) {
	for _, operation := range []string{"execute", "start"} {
		t.Run(operation, func(t *testing.T) {
			defaults := http.Header{"Authorization": {"wrong"}, "Idempotency-Key": {"shared-default"}, "X-Team": {"default"}}
			var keys []string
			var bodies [][]byte
			client := clientFor(t, func(request *http.Request) (*http.Response, error) {
				keys = append(keys, request.Header.Get("Idempotency-Key"))
				body, _ := io.ReadAll(request.Body)
				bodies = append(bodies, body)
				if request.Header.Get("Authorization") != "Bearer test-key" || request.Header.Get("X-Team") != "request" || !strings.HasPrefix(request.Header.Get("User-Agent"), "traceport-go/"+traceport.Version) {
					t.Errorf("headers %v", request.Header)
				}
				if operation == "execute" {
					return response(200, workflowData()), nil
				}
				return response(202, runData("queued")), nil
			}, traceport.WithDefaultHeaders(defaults))
			defaults.Set("Authorization", "changed")
			for _, key := range []string{"job-one", "job-two", ""} {
				options := []traceport.RequestOption{traceport.WithHeaders(http.Header{"AUTHORIZATION": {"wrong"}, "IDEMPOTENCY-KEY": {""}, "X-Team": {"request"}})}
				if key != "" {
					options = append(options, traceport.WithIdempotencyKey(key))
				}
				var err error
				if operation == "execute" {
					_, err = workflows.New(client).Execute(context.Background(), workflows.StartParams{VersionID: versionID}, options...)
				} else {
					_, err = workflows.New(client).Runs.Start(context.Background(), workflows.StartParams{VersionID: versionID}, options...)
				}
				if err != nil {
					t.Fatal(err)
				}
			}
			if keys[0] != "job-one" || keys[1] != "job-two" || len(keys[2]) != 36 {
				t.Errorf("keys: %v", keys)
			}
			assertJSONEqual(t, bodies[0], []byte(`{"configVersionID":"`+versionID+`","additional":{}}`))
		})
	}
	client := clientFor(t, func(request *http.Request) (*http.Response, error) {
		if request.Header.Get("Content-Type") != "" || request.Header.Get("Idempotency-Key") != "" {
			t.Errorf("read headers: %v", request.Header)
		}
		return response(200, runData("running")), nil
	}, traceport.WithDefaultHeaders(http.Header{"Idempotency-Key": {"stray"}}))
	if _, err := workflows.New(client).Runs.Get(context.Background(), runID); err != nil {
		t.Fatal(err)
	}
}

type trackedBody struct {
	io.Reader
	closed *atomic.Int32
}

func (body *trackedBody) Close() error { body.closed.Add(1); return nil }

func TestRetriesPreserveBodyAndKeyAndCloseBodies(t *testing.T) {
	var closed atomic.Int32
	var bodies [][]byte
	var keys []string
	client := clientFor(t, func(request *http.Request) (*http.Response, error) {
		body, _ := io.ReadAll(request.Body)
		bodies = append(bodies, body)
		keys = append(keys, request.Header.Get("Idempotency-Key"))
		reply := response(202, runData("queued"))
		if len(keys) == 1 {
			reply.StatusCode = 503
			reply.Header.Set("Retry-After", "0")
		}
		reply.Body = &trackedBody{Reader: reply.Body, closed: &closed}
		return reply, nil
	}, traceport.WithMaxRetries(2))
	if _, err := workflows.New(client).Runs.Start(context.Background(), workflows.StartParams{VersionID: versionID, Input: map[string]any{"a": 1}}); err != nil {
		t.Fatal(err)
	}
	if len(keys) != 2 || keys[0] == "" || keys[0] != keys[1] || string(bodies[0]) != string(bodies[1]) || closed.Load() != 2 {
		t.Errorf("retry keys=%v body=%q closed=%d", keys, bodies, closed.Load())
	}
}

func TestRetryAfterAndLimit(t *testing.T) {
	calls := 0
	client := clientFor(t, func(*http.Request) (*http.Response, error) {
		calls++
		reply := response(503, nil)
		reply.Header.Set("Retry-After", "0.02")
		return reply, nil
	})
	started := time.Now()
	_, err := workflows.New(client).Runs.Get(context.Background(), runID, traceport.WithRequestMaxRetries(1))
	var server *traceport.InternalServerError
	if !errors.As(err, &server) || calls != 2 || time.Since(started) < 15*time.Millisecond {
		t.Fatalf("calls=%d elapsed=%s error=%v", calls, time.Since(started), err)
	}
}

type contextBody struct {
	ctx    context.Context
	closed *atomic.Int32
}

func (body *contextBody) Read([]byte) (int, error) { <-body.ctx.Done(); return 0, body.ctx.Err() }
func (body *contextBody) Close() error             { body.closed.Add(1); return nil }

func TestFullBodyTimeoutAndRetry(t *testing.T) {
	for _, operation := range []string{"get", "start", "execute"} {
		t.Run(operation, func(t *testing.T) {
			var closed atomic.Int32
			calls := 0
			client := clientFor(t, func(request *http.Request) (*http.Response, error) {
				calls++
				if calls == 1 {
					return &http.Response{StatusCode: 200, Header: make(http.Header), Body: &contextBody{ctx: request.Context(), closed: &closed}}, nil
				}
				return response(200, runData("succeeded")), nil
			}, traceport.WithMaxRetries(1))
			options := []traceport.RequestOption{traceport.WithRequestTimeout(10 * time.Millisecond)}
			var err error
			switch operation {
			case "get":
				_, err = workflows.New(client).Runs.Get(context.Background(), runID, options...)
			case "start":
				_, err = workflows.New(client).Runs.Start(context.Background(), workflows.StartParams{VersionID: versionID}, options...)
			case "execute":
				_, err = workflows.New(client).Execute(context.Background(), workflows.StartParams{VersionID: versionID}, options...)
			}
			if operation == "execute" {
				var timeout *traceport.APITimeoutError
				if !errors.As(err, &timeout) || !errors.Is(err, context.DeadlineExceeded) || calls != 1 {
					t.Fatalf("execute calls=%d error=%v", calls, err)
				}
			} else if err != nil || calls != 2 {
				t.Fatalf("%s calls=%d error=%v", operation, calls, err)
			}
			if closed.Load() != 1 {
				t.Errorf("stalled body closed %d times", closed.Load())
			}
		})
	}
}

func TestExecuteDefaultTimeout(t *testing.T) {
	client := clientFor(t, func(request *http.Request) (*http.Response, error) {
		deadline, ok := request.Context().Deadline()
		if !ok || time.Until(deadline) < 5*time.Minute {
			t.Errorf("execute deadline %v", deadline)
		}
		return response(200, workflowData()), nil
	}, traceport.WithTimeout(time.Second))
	if _, err := workflows.New(client).Execute(context.Background(), workflows.StartParams{VersionID: versionID}); err != nil {
		t.Fatal(err)
	}
}

func TestCancellationAndContextDeadline(t *testing.T) {
	for _, during := range []string{"before", "headers", "body", "backoff"} {
		t.Run(during, func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			var closed atomic.Int32
			calls := 0
			client := clientFor(t, func(request *http.Request) (*http.Response, error) {
				calls++
				switch during {
				case "headers":
					cancel()
					<-request.Context().Done()
					return nil, request.Context().Err()
				case "body":
					time.AfterFunc(time.Millisecond, cancel)
					return &http.Response{StatusCode: 200, Header: make(http.Header), Body: &contextBody{ctx: request.Context(), closed: &closed}}, nil
				default:
					reply := response(503, nil)
					reply.Header.Set("Retry-After", "60")
					time.AfterFunc(time.Millisecond, cancel)
					return reply, nil
				}
			}, traceport.WithMaxRetries(2))
			if during == "before" {
				cancel()
			}
			_, err := workflows.New(client).Runs.Get(ctx, runID)
			var aborted *traceport.RequestAbortedError
			if !errors.As(err, &aborted) || !errors.Is(err, context.Canceled) {
				t.Fatalf("cancellation: %v", err)
			}
			if during == "before" && calls != 0 || during != "before" && calls != 1 {
				t.Errorf("calls %d", calls)
			}
		})
	}
}

type brokenBody struct{ cause error }

func (body brokenBody) Read([]byte) (int, error) { return 0, body.cause }
func (brokenBody) Close() error                  { return nil }

func TestConnectionFailures(t *testing.T) {
	for _, phase := range []string{"connect", "body"} {
		t.Run(phase, func(t *testing.T) {
			cause := errors.New("socket closed")
			calls := 0
			client := clientFor(t, func(*http.Request) (*http.Response, error) {
				calls++
				if phase == "connect" {
					return nil, cause
				}
				return &http.Response{StatusCode: 200, Header: make(http.Header), Body: brokenBody{cause}}, nil
			})
			_, err := workflows.New(client).Runs.Get(context.Background(), runID)
			var connection *traceport.APIConnectionError
			if !errors.As(err, &connection) || !errors.Is(err, cause) || calls != 1 {
				t.Fatalf("connection: %v", err)
			}
		})
	}
}

func TestBodyConnectionFailureRetries(t *testing.T) {
	calls := 0
	client := clientFor(t, func(*http.Request) (*http.Response, error) {
		calls++
		if calls == 1 {
			return &http.Response{StatusCode: 200, Header: make(http.Header), Body: brokenBody{errors.New("connection reset")}}, nil
		}
		return response(200, runData("succeeded")), nil
	}, traceport.WithMaxRetries(1))
	if _, err := workflows.New(client).Runs.Get(context.Background(), runID); err != nil || calls != 2 {
		t.Fatalf("body retry calls=%d err=%v", calls, err)
	}
}

func TestHTTPErrorTypesAndMetadata(t *testing.T) {
	for _, item := range []struct {
		status    int
		name      string
		retryable bool
	}{
		{400, "BadRequestError", false}, {401, "AuthenticationError", false}, {402, "PaymentRequiredError", false},
		{403, "PermissionDeniedError", false}, {404, "NotFoundError", false}, {409, "ConflictError", false},
		{408, "APIError", true}, {422, "APIError", false}, {429, "RateLimitError", true},
		{500, "InternalServerError", true}, {501, "InternalServerError", false}, {502, "InternalServerError", true},
		{503, "InternalServerError", true}, {504, "InternalServerError", true},
	} {
		t.Run(item.name+http.StatusText(item.status), func(t *testing.T) {
			client := clientFor(t, func(*http.Request) (*http.Response, error) {
				reply := response(item.status, nil)
				reply.Header.Set("X-Request-Id", "req_1")
				return reply, nil
			})
			_, err := workflows.New(client).Runs.Get(context.Background(), runID)
			var base *traceport.APIError
			var sdk traceport.TraceportError
			if err == nil || reflect.TypeOf(err).Elem().Name() != item.name || !errors.As(err, &base) || !errors.As(err, &sdk) || base.RequestID != "req_1" || base.Retryable != item.retryable {
				t.Fatalf("HTTP %d: %+v", item.status, err)
			}
		})
	}
}

func TestMalformedSuccessDoesNotRetry(t *testing.T) {
	for _, data := range []string{`ok`, `null`, `{"data":null,"error":"boom"}`, `{"data":{}}`, `{"data":123}`, `{"data":{"items":[null],"limit":50,"offset":0}}`} {
		t.Run(data, func(t *testing.T) {
			calls := 0
			client := clientFor(t, func(*http.Request) (*http.Response, error) {
				calls++
				return &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(data))}, nil
			}, traceport.WithMaxRetries(2))
			_, err := workflows.New(client).Runs.Get(context.Background(), runID)
			var invalid *traceport.InvalidResponseError
			if !errors.As(err, &invalid) || calls != 1 {
				t.Fatalf("calls=%d error=%v", calls, err)
			}
		})
	}
}

func TestConcurrentClientUse(t *testing.T) {
	var calls atomic.Int32
	client := clientFor(t, func(*http.Request) (*http.Response, error) {
		calls.Add(1)
		return response(200, runData("running")), nil
	})
	var workers sync.WaitGroup
	for i := 0; i < 20; i++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			if _, err := workflows.New(client).Runs.Get(context.Background(), runID); err != nil {
				t.Error(err)
			}
		}()
	}
	workers.Wait()
	if calls.Load() != 20 {
		t.Errorf("calls %d", calls.Load())
	}
}
