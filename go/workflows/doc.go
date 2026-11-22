// Package workflows is the Traceport workflows product: run saved workflows synchronously,
// or as durable background runs.
//
// It takes the shared client from the root traceport package, so you configure the API key,
// base URL, timeouts and retries once for every product:
//
//	client, err := traceport.NewClient() // github.com/traceport-ai/sdks/go
//	if err != nil { ... }
//	wf := workflows.New(client)
//	result, err := wf.Execute(ctx, workflows.StartParams{VersionID: versionID})
//
// Execute returns workflow failures as normal results with Status RunFailed; request
// failures return the typed errors from the traceport package. RequireOutput opts into a
// FailedError instead. Cancelling observation never cancels an accepted run on the server.
package workflows
