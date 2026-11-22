package workflows

import (
	"encoding/json"
	"time"
)

// RunStatus describes durable execution state.
type RunStatus string

const (
	RunQueued      RunStatus = "queued"
	RunRunning     RunStatus = "running"
	RunSucceeded   RunStatus = "succeeded"
	RunFailed      RunStatus = "failed"
	RunInterrupted RunStatus = "interrupted"
)

// Terminal reports whether a run has finished.
func (status RunStatus) Terminal() bool {
	return status == RunSucceeded || status == RunFailed || status == RunInterrupted
}

// RunMode distinguishes published workflows and dashboard draft tests.
type RunMode string

const (
	ModeProduction RunMode = "production"
	ModeDraftTest  RunMode = "draft_test"
)

// BillingMethod identifies how the execution was paid for.
type BillingMethod string

const (
	BillingIncluded BillingMethod = "included"
	BillingWallet   BillingMethod = "wallet"
	BillingInvoice  BillingMethod = "invoice"
)

// RunBilling is the immutable first-processing billing receipt.
type RunBilling struct {
	Method      BillingMethod `json:"method"`
	PeriodMonth string        `json:"periodMonth"`
	Currency    string        `json:"currency"`
	AmountUSD   string        `json:"amountUsd"`
	CreditedAt  *time.Time    `json:"creditedAt,omitempty"`
}

// Step retains known fields and every original field in Raw.
type Step struct {
	Index      int                        `json:"index"`
	NodeID     string                     `json:"nodeId"`
	Name       string                     `json:"name"`
	Type       string                     `json:"type"`
	Attempt    int                        `json:"attempt"`
	Status     string                     `json:"status"`
	StartedAt  *time.Time                 `json:"startedAt,omitempty"`
	DurationMS float64                    `json:"durationMs"`
	Input      map[string]any             `json:"input,omitempty"`
	Output     any                        `json:"output,omitempty"`
	Error      string                     `json:"error,omitempty"`
	Raw        map[string]json.RawMessage `json:"-"`
}

// UnmarshalJSON preserves additive fields such as usage, dependencies and tool calls.
func (step *Step) UnmarshalJSON(data []byte) error {
	type plain Step
	var decoded plain
	if err := json.Unmarshal(data, &decoded); err != nil {
		return err
	}
	if err := json.Unmarshal(data, &decoded.Raw); err != nil {
		return err
	}
	*step = Step(decoded)
	return nil
}

// Result interprets an execution outcome. A failed workflow returned with
// HTTP 200 is a normal result with Status RunFailed, not a request error.
type Result struct {
	Status RunStatus      `json:"status"`
	Output any            `json:"output"`
	Error  string         `json:"error,omitempty"`
	Data   map[string]any `json:"data"`
	Steps  []Step         `json:"steps"`
}

// Run is a durable workflow resource. Raw preserves additive wire fields.
// Lists return summaries without Output or Result.
type Run struct {
	ID              string                     `json:"id"`
	ConfigVersionID string                     `json:"configVersionID"`
	Revision        int64                      `json:"revision"`
	Status          RunStatus                  `json:"status"`
	Mode            RunMode                    `json:"mode"`
	Source          string                     `json:"source"`
	CreatedAt       time.Time                  `json:"createdAt"`
	StartedAt       *time.Time                 `json:"startedAt,omitempty"`
	FinishedAt      *time.Time                 `json:"finishedAt,omitempty"`
	Error           string                     `json:"error,omitempty"`
	FailureOrigin   string                     `json:"failureOrigin,omitempty"`
	Billing         *RunBilling                `json:"billing,omitempty"`
	Output          map[string]any             `json:"output,omitempty"`
	Result          *Result                    `json:"-"`
	Raw             map[string]json.RawMessage `json:"-"`
}

// RunPage contains runs newest first. It has no total-count guarantee.
type RunPage struct {
	Items  []Run `json:"items"`
	Limit  int   `json:"limit"`
	Offset int   `json:"offset"`
}

// StartParams is shared by Execute and Runs.Start. A nil Input sends {}.
type StartParams struct {
	VersionID string
	Input     map[string]any
}

// ListRunsParams filters runs. Nil Limit/Offset use the server defaults.
// Use Int to distinguish an explicit zero from an omitted query parameter.
type ListRunsParams struct {
	VersionID string
	Status    RunStatus
	Limit     *int
	Offset    *int
}

// Int returns a pointer for an optional integer query parameter.
func Int(value int) *int { return &value }

// WaitOptions controls observation. Zero values use defaults: ten minutes,
// one second and five seconds respectively. Per-request options control each read.
type WaitOptions struct {
	Timeout         time.Duration
	PollInterval    time.Duration
	MaxPollInterval time.Duration
}
