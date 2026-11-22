package workflows

import (
	"context"
	"encoding/json"
	"errors"
	"net/url"
	"strconv"
	"time"

	traceport "github.com/traceport-ai/sdks/go"
	"github.com/traceport-ai/sdks/go/internal/core"
)

// RunsService starts and observes durable workflow runs.
type RunsService struct{ client *core.Client }

// Start admits a run and returns immediately, usually queued. A stable generated
// or caller-provided idempotency key is reused on every retry, including timeouts.
func (service *RunsService) Start(ctx context.Context, params StartParams, options ...traceport.RequestOption) (*Run, error) {
	body, err := startBody(params)
	if err != nil {
		return nil, err
	}
	response, err := core.Do(ctx, service.client, core.Request{Method: "POST", Path: "/workflow/runs", Body: body, Mutation: true, RetryOnTimeout: true}, options...)
	if err != nil {
		return nil, err
	}
	return parseRun(response.Data, response.Status)
}

// Get reads a run. Failed and interrupted runs are normal resources, not errors.
func (service *RunsService) Get(ctx context.Context, runID string, options ...traceport.RequestOption) (*Run, error) {
	if err := core.ValidateID(runID, "runId"); err != nil {
		return nil, err
	}
	response, err := core.Do(ctx, service.client, core.Request{Method: "GET", Path: "/workflow/runs/" + url.PathEscape(runID), RetryOnTimeout: true}, options...)
	if err != nil {
		return nil, err
	}
	return parseRun(response.Data, response.Status)
}

// List returns run summaries newest first, without stored output or interpreted results.
func (service *RunsService) List(ctx context.Context, params ListRunsParams, options ...traceport.RequestOption) (*RunPage, error) {
	query := make(url.Values)
	if params.VersionID != "" {
		query.Set("configVersionID", params.VersionID)
	}
	if params.Status != "" {
		query.Set("status", string(params.Status))
	}
	if params.Limit != nil {
		query.Set("limit", strconv.Itoa(*params.Limit))
	}
	if params.Offset != nil {
		query.Set("offset", strconv.Itoa(*params.Offset))
	}
	response, err := core.Do(ctx, service.client, core.Request{Method: "GET", Path: "/workflow/runs", Query: query, RetryOnTimeout: true}, options...)
	if err != nil {
		return nil, err
	}
	var wire struct {
		Items  *[]json.RawMessage `json:"items"`
		Limit  *int               `json:"limit"`
		Offset *int               `json:"offset"`
	}
	if json.Unmarshal(response.Data, &wire) != nil || wire.Items == nil || wire.Limit == nil || wire.Offset == nil || *wire.Limit < 1 || *wire.Offset < 0 {
		return nil, &core.InvalidResponseError{Message: "response is not a run page", StatusCode: response.Status, Body: core.ParseBody(response.Data)}
	}
	page := &RunPage{Items: make([]Run, 0, len(*wire.Items)), Limit: *wire.Limit, Offset: *wire.Offset}
	for _, item := range *wire.Items {
		run, err := parseRun(item, response.Status)
		if err != nil {
			return nil, err
		}
		page.Items = append(page.Items, *run)
	}
	return page, nil
}

var waitDeadline = errors.New("traceport observation deadline")

// WaitForCompletion polls until succeeded, failed or interrupted. One observation
// deadline bounds reads, retries and sleeps. A timeout never cancels the remote run.
// WithRequestTimeout sets each read's timeout independently of WaitOptions.Timeout.
func (service *RunsService) WaitForCompletion(ctx context.Context, runID string, wait WaitOptions, options ...traceport.RequestOption) (*Run, error) {
	if ctx == nil {
		return nil, core.Invalid("context", "must not be nil")
	}
	if err := core.ValidateID(runID, "runId"); err != nil {
		return nil, err
	}
	if err := core.ValidateRequestOptions(options...); err != nil {
		return nil, err
	}
	if wait.Timeout == 0 {
		wait.Timeout = 10 * time.Minute
	}
	if wait.PollInterval == 0 {
		wait.PollInterval = time.Second
	}
	if wait.MaxPollInterval == 0 {
		wait.MaxPollInterval = 5 * time.Second
	}
	for field, value := range map[string]time.Duration{"timeout": wait.Timeout, "pollInterval": wait.PollInterval, "maxPollInterval": wait.MaxPollInterval} {
		if err := core.ValidateDuration(value, field); err != nil {
			return nil, err
		}
	}
	if ctx.Err() != nil {
		return nil, &core.RequestAbortedError{Cause: context.Cause(ctx)}
	}
	observer, cancel := context.WithTimeoutCause(ctx, wait.Timeout, waitDeadline)
	defer cancel()
	deadline := time.Now().Add(wait.Timeout)
	interval := min(wait.PollInterval, wait.MaxPollInterval)
	var last *Run
	checkDeadline := func() error {
		if ctx.Err() != nil {
			return &core.RequestAbortedError{Cause: context.Cause(ctx)}
		}
		if errors.Is(context.Cause(observer), waitDeadline) || !time.Now().Before(deadline) {
			return &WaitTimeoutError{RunID: runID, LastRun: last, Timeout: wait.Timeout}
		}
		return nil
	}
	for {
		if err := checkDeadline(); err != nil {
			return nil, err
		}
		run, err := service.Get(observer, runID, options...)
		if deadlineErr := checkDeadline(); deadlineErr != nil {
			return nil, deadlineErr
		}
		if err != nil {
			return nil, err
		}
		last = run
		if run.Status.Terminal() {
			return run, nil
		}
		if err := core.Sleep(observer, min(interval, time.Until(deadline))); err != nil {
			if deadlineErr := checkDeadline(); deadlineErr != nil {
				return nil, deadlineErr
			}
			return nil, err
		}
		// Avoid duration overflow while capping exponential polling backoff.
		increment := interval / 2
		if increment >= wait.MaxPollInterval-interval {
			interval = wait.MaxPollInterval
		} else {
			interval += increment
		}
	}
}
