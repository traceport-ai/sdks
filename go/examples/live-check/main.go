// Explicitly run against a sandbox API. These real executions consume workflow usage.
// Needs TRACEPORT_API_KEY, TRACEPORT_BASE_URL and TRACEPORT_CONFORMANCE_VERSION_OK/FAIL.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"reflect"
	"time"

	traceport "github.com/traceport-ai/sdks/go"
	"github.com/traceport-ai/sdks/go/workflows"
)

func main() {
	if err := check(); err != nil {
		fmt.Fprintln(os.Stderr, "FAIL:", err)
		os.Exit(1)
	}
}

func check() error {
	okVersion, failVersion := os.Getenv("TRACEPORT_CONFORMANCE_VERSION_OK"), os.Getenv("TRACEPORT_CONFORMANCE_VERSION_FAIL")
	if okVersion == "" || failVersion == "" {
		return errors.New("set TRACEPORT_CONFORMANCE_VERSION_OK and TRACEPORT_CONFORMANCE_VERSION_FAIL")
	}
	client, err := traceport.NewClient()
	if err != nil {
		return err
	}
	// One client serves every Traceport product; each product package takes it.
	wf := workflows.New(client)
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	params := workflows.StartParams{VersionID: okVersion, Input: map[string]any{"question": "SDK live check"}}
	result, err := wf.Execute(ctx, params)
	if err != nil {
		return fmt.Errorf("C-01: %w", err)
	}
	if result.Status != workflows.RunSucceeded {
		return fmt.Errorf("C-01: unexpected status %s: %s", result.Status, result.Error)
	}
	fmt.Println("PASS C-01 execute success")
	failed, err := wf.Execute(ctx, workflows.StartParams{VersionID: failVersion, Input: params.Input})
	if err != nil {
		return fmt.Errorf("C-02: %w", err)
	}
	if failed.Status != workflows.RunFailed || failed.Error == "" {
		return errors.New("C-02: expected workflow failure")
	}
	fmt.Println("PASS C-02 workflow failure is a normal outcome")
	badClient, err := traceport.NewClient(traceport.WithAPIKey("invalid-sdk-test-key"), traceport.WithMaxRetries(0))
	if err != nil {
		return err
	}
	_, err = workflows.New(badClient).Execute(ctx, params)
	var authentication *traceport.AuthenticationError
	if !errors.As(err, &authentication) {
		return fmt.Errorf("C-03: expected authentication error, got %v", err)
	}
	fmt.Println("PASS C-03 authentication error")
	var bytes [16]byte
	if _, err := rand.Read(bytes[:]); err != nil {
		return err
	}
	key := hex.EncodeToString(bytes[:])
	run, err := wf.Runs.Start(ctx, params, traceport.WithIdempotencyKey(key))
	if err != nil {
		return fmt.Errorf("C-04 start: %w", err)
	}
	finished, err := wf.Runs.WaitForCompletion(ctx, run.ID, workflows.WaitOptions{Timeout: 2 * time.Minute})
	if err != nil {
		return fmt.Errorf("C-04 wait: %w", err)
	}
	if finished.ID != run.ID || finished.Status != workflows.RunSucceeded {
		return fmt.Errorf("C-04: run %s status %s", finished.ID, finished.Status)
	}
	if _, err := finished.RequireOutput(); err != nil {
		return fmt.Errorf("C-04 output: %w", err)
	}
	fmt.Println("PASS C-04 durable start and completion")
	replayed, err := wf.Runs.Start(ctx, params, traceport.WithIdempotencyKey(key))
	if err != nil {
		return fmt.Errorf("C-05: %w", err)
	}
	if replayed.ID != run.ID {
		return errors.New("C-05: replay created another run")
	}
	fmt.Println("PASS C-05 same-key replay")
	_, err = wf.Runs.Start(ctx, workflows.StartParams{VersionID: okVersion, Input: map[string]any{"question": "different"}}, traceport.WithIdempotencyKey(key))
	var conflict *traceport.ConflictError
	if !errors.As(err, &conflict) {
		return fmt.Errorf("C-06: expected conflict, got %v", err)
	}
	fmt.Println("PASS C-06 changed input conflicts")
	observed, err := wf.Runs.Start(ctx, params)
	if err != nil {
		return fmt.Errorf("C-07 start: %w", err)
	}
	_, err = wf.Runs.WaitForCompletion(ctx, observed.ID, workflows.WaitOptions{Timeout: time.Millisecond})
	var timeout *workflows.WaitTimeoutError
	if err == nil {
		fmt.Println("SKIP C-07 run already terminal; use a slower workflow")
	} else if !errors.As(err, &timeout) {
		return fmt.Errorf("C-07: expected wait timeout, got %v", err)
	} else {
		if _, err := wf.Runs.WaitForCompletion(ctx, observed.ID, workflows.WaitOptions{Timeout: 2 * time.Minute}); err != nil {
			return fmt.Errorf("C-07 continued observation: %w", err)
		}
		fmt.Println("PASS C-07 observation timeout leaves run alive")
	}
	page, err := wf.Runs.List(ctx, workflows.ListRunsParams{VersionID: okVersion, Status: workflows.RunSucceeded, Limit: workflows.Int(2), Offset: workflows.Int(0)})
	if err != nil {
		return fmt.Errorf("C-08: %w", err)
	}
	if len(page.Items) == 0 || len(page.Items) > 2 || page.Limit != 2 || page.Offset != 0 {
		return errors.New("C-08: invalid page")
	}
	for i, item := range page.Items {
		if item.ConfigVersionID != okVersion || item.Status != workflows.RunSucceeded || item.Output != nil {
			return errors.New("C-08: invalid summary or filter")
		}
		if i > 0 && item.CreatedAt.After(page.Items[i-1].CreatedAt) {
			return errors.New("C-08: page is not newest first")
		}
	}
	fmt.Println("PASS C-08 filtered page")
	// Also prove synchronous replay uses its saved result.
	first, err := wf.Execute(ctx, params, traceport.WithIdempotencyKey(key+"-sync"))
	if err != nil {
		return err
	}
	second, err := wf.Execute(ctx, params, traceport.WithIdempotencyKey(key+"-sync"))
	if err != nil {
		return err
	}
	if !reflect.DeepEqual(first.Output, second.Output) {
		return errors.New("synchronous replay output changed")
	}
	fmt.Println("PASS synchronous replay")
	return nil
}
