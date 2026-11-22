package workflows

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/traceport-ai/sdks/go/internal/core"
)

func parseResult(raw json.RawMessage, status int) (*Result, error) {
	var wire struct {
		Data  map[string]any `json:"data"`
		Error string         `json:"error"`
		Steps []Step         `json:"steps"`
	}
	if err := json.Unmarshal(raw, &wire); err != nil || wire.Data == nil {
		return nil, &core.InvalidResponseError{Message: "response does not contain a workflow result", StatusCode: status, Body: core.ParseBody(raw)}
	}
	output := any(wire.Data)
	if final, ok := wire.Data["final"].(map[string]any); ok && len(final) > 0 {
		output = final
	}
	if wire.Steps == nil {
		wire.Steps = []Step{}
	}
	result := &Result{Status: RunSucceeded, Output: output, Data: wire.Data, Steps: wire.Steps, Error: strings.TrimSpace(wire.Error)}
	if result.Error != "" {
		result.Status = RunFailed
	}
	return result, nil
}

// RequireOutput returns successful output or a FailedError retaining partial results.
func (result *Result) RequireOutput() (any, error) {
	if result == nil {
		return nil, core.Invalid("result", "must not be nil")
	}
	if result.Status == RunSucceeded {
		return result.Output, nil
	}
	message := result.Error
	if message == "" {
		message = "workflow failed"
	}
	return nil, &FailedError{Message: message, Status: RunFailed, Result: result}
}

// RequireOutput requires a successful run with an interpreted result. Read summaries
// with Runs.Get first; queued, running, failed and interrupted runs return an error.
func (run *Run) RequireOutput() (any, error) {
	if run == nil {
		return nil, core.Invalid("run", "must not be nil")
	}
	if run.Status == RunSucceeded && run.Result != nil && run.Result.Status == RunSucceeded {
		return run.Result.Output, nil
	}
	message := run.Error
	if message == "" && run.Result != nil {
		message = run.Result.Error
	}
	if message == "" {
		if run.Status == RunSucceeded {
			message = fmt.Sprintf("run %s has no output; read it with Runs.Get", run.ID)
		} else {
			message = fmt.Sprintf("run %s is %s", run.ID, run.Status)
		}
	}
	return nil, &FailedError{Message: message, RunID: run.ID, Status: run.Status, Result: run.Result}
}

func parseRun(raw json.RawMessage, status int) (*Run, error) {
	var fields map[string]json.RawMessage
	var run Run
	valid := json.Unmarshal(raw, &fields) == nil && fields != nil
	for _, field := range []string{"id", "configVersionID", "revision", "status", "mode", "source", "createdAt"} {
		if len(fields[field]) == 0 || string(fields[field]) == "null" {
			valid = false
		}
	}
	if !valid || json.Unmarshal(raw, &run) != nil || strings.TrimSpace(run.ID) == "" || strings.TrimSpace(run.ConfigVersionID) == "" || run.Revision < 0 || !validRunStatus(run.Status) || (run.Mode != ModeProduction && run.Mode != ModeDraftTest) || run.CreatedAt.IsZero() {
		return nil, &core.InvalidResponseError{Message: "response is not a workflow run", StatusCode: status, Body: core.ParseBody(raw)}
	}
	run.Raw = fields
	if run.Output != nil {
		output, _ := json.Marshal(run.Output)
		// New stored-output shapes remain available even if they cannot be interpreted yet.
		run.Result, _ = parseResult(output, status)
	}
	return &run, nil
}

func validRunStatus(status RunStatus) bool {
	return status == RunQueued || status == RunRunning || status.Terminal()
}
