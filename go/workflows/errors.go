package workflows

import (
	"context"
	"fmt"
	"time"

	"github.com/traceport-ai/sdks/go/internal/core"
)

// FailedError is returned only by RequireOutput, never by Execute/Get/WaitForCompletion.
type FailedError struct {
	core.ErrorMarker
	Message string
	RunID   string
	Status  RunStatus
	Result  *Result
}

func (e *FailedError) Error() string { return e.Message }

// WaitTimeoutError stops observation without cancelling the server-side run.
// LastRun is nil when no status was read before the observation deadline.
type WaitTimeoutError struct {
	core.ErrorMarker
	RunID   string
	LastRun *Run
	Timeout time.Duration
}

func (e *WaitTimeoutError) Error() string {
	status := "no status received"
	if e.LastRun != nil {
		status = "last status: " + string(e.LastRun.Status)
	}
	return fmt.Sprintf("traceport: run %s did not finish within %s (%s)", e.RunID, e.Timeout, status)
}

// Unwrap makes observation expiry recognizable with errors.Is(err, context.DeadlineExceeded).
func (*WaitTimeoutError) Unwrap() error { return context.DeadlineExceeded }

var (
	_ core.TraceportError = (*FailedError)(nil)
	_ core.TraceportError = (*WaitTimeoutError)(nil)
)
