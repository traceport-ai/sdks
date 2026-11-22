package workflows

import (
	"context"
	"time"

	traceport "github.com/traceport-ai/sdks/go"
	"github.com/traceport-ai/sdks/go/internal/core"
)

// Service executes saved workflows and provides durable Runs.
type Service struct {
	Runs   *RunsService
	client *core.Client
}

func startBody(params StartParams) (any, error) {
	if err := core.ValidateID(params.VersionID, "versionId"); err != nil {
		return nil, err
	}
	input := params.Input
	if input == nil {
		input = map[string]any{}
	}
	return struct {
		VersionID string         `json:"configVersionID"`
		Input     map[string]any `json:"additional"`
	}{params.VersionID, input}, nil
}

// Execute runs a published workflow synchronously. Workflow failures resolve as
// results with Status RunFailed. A timed-out Execute is never retried because the
// server may still be running it. All other retries preserve the key and body.
func (service *Service) Execute(ctx context.Context, params StartParams, options ...traceport.RequestOption) (*Result, error) {
	body, err := startBody(params)
	if err != nil {
		return nil, err
	}
	response, err := core.Do(ctx, service.client, core.Request{Method: "POST", Path: "/workflow/execute", Body: body, Mutation: true, MinimumTimeout: 6 * time.Minute}, options...)
	if err != nil {
		return nil, err
	}
	return parseResult(response.Data, response.Status)
}

// New returns the workflows product for a shared client from traceport.NewClient. Every call
// uses that client's credentials, base URL, HTTP client, timeouts and retries; no second
// client or configuration is needed. To give workflows different timeouts or retries, pass a
// client derived with client.WithOptions.
//
// A nil client is reported as a ValidationError by the first call.
func New(client *traceport.Client) *Service {
	return &Service{client: client, Runs: &RunsService{client: client}}
}
