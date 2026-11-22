// Start a durable workflow and observe it without cancelling server-side work on timeout.
package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"time"

	traceport "github.com/traceport-ai/sdks/go"
	"github.com/traceport-ai/sdks/go/workflows"
)

func main() {
	client, err := traceport.NewClient()
	if err != nil {
		log.Fatal(err)
	}
	// One client serves every Traceport product; each product package takes it.
	wf := workflows.New(client)
	ctx := context.Background()
	// Persist a stable key with your job to retry safely across process restarts.
	key := os.Getenv("TRACEPORT_JOB_ID")
	if key == "" {
		log.Fatal("set TRACEPORT_JOB_ID to a stable ID for this logical job")
	}
	run, err := wf.Runs.Start(ctx, workflows.StartParams{
		VersionID: os.Getenv("TRACEPORT_VERSION_ID"), Input: map[string]any{"question": "Hello"},
	}, traceport.WithIdempotencyKey(key))
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("started", run.ID, run.Status)
	finished, err := wf.Runs.WaitForCompletion(ctx, run.ID, workflows.WaitOptions{Timeout: 2 * time.Minute})
	if err != nil {
		var timeout *workflows.WaitTimeoutError
		if errors.As(err, &timeout) {
			fmt.Println("observation timed out; read the run later:", timeout.RunID)
			if timeout.LastRun != nil {
				fmt.Println("last status:", timeout.LastRun.Status)
			}
			return
		}
		log.Fatal(err)
	}
	output, err := finished.RequireOutput()
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(output)
}
