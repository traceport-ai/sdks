// Run with TRACEPORT_API_KEY and TRACEPORT_VERSION_ID set.
package main

import (
	"context"
	"fmt"
	"log"
	"os"

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
	result, err := wf.Execute(context.Background(), workflows.StartParams{
		VersionID: os.Getenv("TRACEPORT_VERSION_ID"),
		Input:     map[string]any{"question": "What is Traceport?"},
	})
	if err != nil {
		log.Fatal(err)
	}
	if result.Status == workflows.RunFailed {
		log.Printf("workflow failed: %s; partial output: %v", result.Error, result.Output)
		return
	}
	fmt.Println(result.Output)
}
