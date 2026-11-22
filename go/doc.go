// Package traceport is the shared client for the Traceport Go SDK.
//
// Create one Client with NewClient and pass it to the product packages you use. Each
// product lives in its own package and imports only what it needs:
//
//	client, err := traceport.NewClient() // reads TRACEPORT_API_KEY
//	if err != nil { ... }
//	wf := workflows.New(client)         // github.com/traceport-ai/sdks/go/workflows
//
// This package holds what every product shares: client configuration, request options and
// request errors. Request failures return typed errors; use errors.As to inspect them.
// Every call accepts a context.
package traceport
