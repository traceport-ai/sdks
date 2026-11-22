package test

import (
	"context"
	"errors"
	"net/http"
	"testing"
	"time"

	traceport "github.com/traceport-ai/sdks/go"
	"github.com/traceport-ai/sdks/go/workflows"
)

func TestWaitForCompletion(t *testing.T) {
	for _, terminal := range []string{"succeeded", "failed", "interrupted"} {
		t.Run(terminal, func(t *testing.T) {
			calls := 0
			client := clientFor(t, func(*http.Request) (*http.Response, error) {
				calls++
				status := "running"
				if calls == 3 {
					status = terminal
				}
				return response(200, runData(status)), nil
			})
			result, err := workflows.New(client).Runs.WaitForCompletion(context.Background(), runID, workflows.WaitOptions{Timeout: time.Second, PollInterval: time.Millisecond, MaxPollInterval: 2 * time.Millisecond})
			if err != nil || string(result.Status) != terminal || calls != 3 {
				t.Fatalf("result=%+v calls=%d error=%v", result, calls, err)
			}
		})
	}
}

func TestWaitDeadlineBoundsFirstRead(t *testing.T) {
	client := clientFor(t, func(request *http.Request) (*http.Response, error) {
		<-request.Context().Done()
		return nil, request.Context().Err()
	}, traceport.WithMaxRetries(2))
	started := time.Now()
	_, err := workflows.New(client).Runs.WaitForCompletion(context.Background(), runID, workflows.WaitOptions{Timeout: 20 * time.Millisecond})
	var timeout *workflows.WaitTimeoutError
	if !errors.As(err, &timeout) || !errors.Is(err, context.DeadlineExceeded) || timeout.LastRun != nil || timeout.RunID != runID || time.Since(started) > time.Second {
		t.Fatalf("deadline: %v", err)
	}
}

func TestWaitDeadlineDuringSleepAndBackoff(t *testing.T) {
	for _, phase := range []string{"sleep", "backoff", "read"} {
		t.Run(phase, func(t *testing.T) {
			calls := 0
			client := clientFor(t, func(request *http.Request) (*http.Response, error) {
				calls++
				if phase == "backoff" && calls > 1 {
					reply := response(503, nil)
					reply.Header.Set("Retry-After", "60")
					return reply, nil
				}
				if phase == "read" && calls > 1 {
					<-request.Context().Done()
					return nil, request.Context().Err()
				}
				return response(200, runData("running")), nil
			}, traceport.WithMaxRetries(2))
			interval := 100 * time.Millisecond
			if phase != "sleep" {
				interval = time.Millisecond
			}
			_, err := workflows.New(client).Runs.WaitForCompletion(context.Background(), runID, workflows.WaitOptions{Timeout: 25 * time.Millisecond, PollInterval: interval})
			var timeout *workflows.WaitTimeoutError
			if !errors.As(err, &timeout) || timeout.LastRun == nil || timeout.LastRun.Status != workflows.RunRunning {
				t.Fatalf("last run: %v", err)
			}
			if phase == "sleep" && calls != 1 || phase != "sleep" && calls != 2 {
				t.Errorf("calls %d", calls)
			}
		})
	}
}

func TestWaitRejectsLateTerminalResponse(t *testing.T) {
	client := clientFor(t, func(*http.Request) (*http.Response, error) {
		// Simulate a slow transport which delivers a response after its context expires.
		time.Sleep(20 * time.Millisecond)
		return response(200, runData("succeeded")), nil
	})
	_, err := workflows.New(client).Runs.WaitForCompletion(context.Background(), runID, workflows.WaitOptions{Timeout: 5 * time.Millisecond})
	var timeout *workflows.WaitTimeoutError
	if !errors.As(err, &timeout) {
		t.Fatalf("late terminal response accepted: %v", err)
	}
}

func TestWaitCallerCancellationAndRequestTimeout(t *testing.T) {
	for _, kind := range []string{"cancelled", "caller deadline", "request timeout"} {
		t.Run(kind, func(t *testing.T) {
			client := clientFor(t, func(request *http.Request) (*http.Response, error) {
				<-request.Context().Done()
				return nil, request.Context().Err()
			})
			ctx := context.Background()
			var cancel context.CancelFunc
			var options []traceport.RequestOption
			if kind == "request timeout" {
				options = append(options, traceport.WithRequestTimeout(5*time.Millisecond))
			} else if kind == "caller deadline" {
				ctx, cancel = context.WithTimeout(ctx, 5*time.Millisecond)
				defer cancel()
			} else {
				ctx, cancel = context.WithCancel(ctx)
				defer cancel()
				time.AfterFunc(5*time.Millisecond, cancel)
			}
			_, err := workflows.New(client).Runs.WaitForCompletion(ctx, runID, workflows.WaitOptions{Timeout: time.Second}, options...)
			if kind == "request timeout" {
				var timeout *traceport.APITimeoutError
				if !errors.As(err, &timeout) {
					t.Fatalf("request timeout: %v", err)
				}
			} else {
				var aborted *traceport.RequestAbortedError
				if !errors.As(err, &aborted) || !errors.Is(err, ctx.Err()) {
					t.Fatalf("caller cancellation: %v", err)
				}
			}
		})
	}
}

func TestWaitOptionsValidation(t *testing.T) {
	client := clientFor(t, func(*http.Request) (*http.Response, error) { t.Fatal("unexpected HTTP"); return nil, nil })
	for _, options := range []workflows.WaitOptions{{Timeout: -1}, {PollInterval: -1}, {MaxPollInterval: -1}} {
		_, err := workflows.New(client).Runs.WaitForCompletion(context.Background(), runID, options)
		var invalid *traceport.ValidationError
		if !errors.As(err, &invalid) {
			t.Fatalf("invalid wait accepted: %v", err)
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := workflows.New(client).Runs.WaitForCompletion(ctx, runID, workflows.WaitOptions{}); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancelled wait: %v", err)
	}
}

func TestRunValidationAcrossOperations(t *testing.T) {
	for _, operation := range []string{"start", "get", "list"} {
		for _, field := range []string{"id", "configVersionID", "revision", "status", "mode", "source", "createdAt"} {
			t.Run(operation+"/missing_"+field, func(t *testing.T) {
				data := runData("running")
				delete(data, field)
				status := 200
				if operation == "start" {
					status = 202
				}
				var payload any = data
				if operation == "list" {
					payload = map[string]any{"items": []any{data}, "limit": 50, "offset": 0}
				}
				client := clientFor(t, func(*http.Request) (*http.Response, error) { return response(status, payload), nil })
				var err error
				switch operation {
				case "start":
					_, err = workflows.New(client).Runs.Start(context.Background(), workflows.StartParams{VersionID: versionID})
				case "get":
					_, err = workflows.New(client).Runs.Get(context.Background(), runID)
				case "list":
					_, err = workflows.New(client).Runs.List(context.Background(), workflows.ListRunsParams{})
				}
				var invalid *traceport.InvalidResponseError
				if !errors.As(err, &invalid) || invalid.StatusCode != status {
					t.Fatalf("invalid run: %v", err)
				}
			})
		}
	}
}

func TestRequireOutputAndRawFields(t *testing.T) {
	data := runData("succeeded")
	data["newServerField"] = "preserved"
	output := workflowData()
	output["steps"] = []any{map[string]any{"nodeId": "node", "usage": map[string]any{"tokens": 12}}}
	data["output"] = output
	client := clientFor(t, func(*http.Request) (*http.Response, error) { return response(200, data), nil })
	run, err := workflows.New(client).Runs.Get(context.Background(), runID)
	if err != nil {
		t.Fatal(err)
	}
	value, err := run.RequireOutput()
	if err != nil || value.(map[string]any)["ok"] != true || string(run.Raw["newServerField"]) != `"preserved"` || string(run.Result.Steps[0].Raw["usage"]) != `{"tokens":12}` {
		t.Fatalf("output/raw: %+v %v", run, err)
	}
	for _, status := range []workflows.RunStatus{workflows.RunQueued, workflows.RunRunning, workflows.RunFailed, workflows.RunInterrupted, workflows.RunSucceeded} {
		_, err := (&workflows.Run{ID: runID, Status: status}).RequireOutput()
		var failed *workflows.FailedError
		if !errors.As(err, &failed) || failed.RunID != runID {
			t.Errorf("RequireOutput(%s): %v", status, err)
		}
	}
	partial := &workflows.Result{Status: workflows.RunFailed, Error: "boom", Output: map[string]any{"partial": true}}
	_, err = partial.RequireOutput()
	var failed *workflows.FailedError
	if !errors.As(err, &failed) || failed.Result != partial {
		t.Fatalf("lost partial result: %v", err)
	}
	data["output"] = map[string]any{"futureOutputShape": true}
	run, err = workflows.New(client).Runs.Get(context.Background(), runID)
	if err != nil || run.Output == nil || run.Result != nil {
		t.Fatalf("unknown stored output: %+v %v", run, err)
	}
}
