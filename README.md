# Traceport SDKs

Official Traceport client libraries for TypeScript, Go and Python, maintained in one repository.

> **Status: pre-release.** No package has been published yet. Nothing here is ready for production use.

Every SDK has the same shape: **one shared client and a module per product**. You install or
import only the products you use, and every product takes the same client, so the API key, base
URL, timeouts and retries are configured once. Adding a product later never needs a second client.

| Language   | Shared client                                   | Workflows product                           | Status                                             |
| ---------- | ----------------------------------------------- | ------------------------------------------- | -------------------------------------------------- |
| TypeScript | `@traceport/core`                               | `@traceport/workflows`                      | Workflows implemented; locally verified            |
| Go         | `github.com/traceport-ai/sdks/go` (`traceport`) | `github.com/traceport-ai/sdks/go/workflows` | Workflows implemented; locally verified            |
| Python     | `traceport-ai` (import `traceport_ai`)          | `traceport_ai.workflows`                    | Sync/async workflows implemented; locally verified |

Docs: [TypeScript](./typescript/README.md) · [Go](./go/README.md) ([changelog](./go/CHANGELOG.md)) · [Python](./python/README.md) ([changelog](./python/CHANGELOG.md)). TypeScript packages each have their own README and changelog under `typescript/packages/`. The npm scope is not yet reserved; the PyPI name `traceport-ai` is free but not yet registered.

| Language   | Create the client                            | Use workflows                                                |
| ---------- | -------------------------------------------- | ------------------------------------------------------------ |
| TypeScript | `const client = new Traceport()`             | `new Workflows(client).execute(...)`                         |
| Go         | `client, err := traceport.NewClient()`       | `workflows.New(client).Execute(ctx, ...)`                    |
| Python     | `client = Traceport()` or `AsyncTraceport()` | `Workflows(client).execute(...)` or `AsyncWorkflows(client)` |

To give one product different timeouts or retries, derive a client that keeps the same
credentials and connections: `client.withOptions(...)`, `client.WithOptions(...)` or
`client.with_options(...)`.

Each workflows product supports execution and durable runs, including bounded polling of
existing runs.

Document parsing and Human input remain planned. Document parsing will ship as its own
product module in each language (taking the same client) after the backend APIs exist. Live conformance and publication remain pending for all clients.

## Repository layout

```
contract/      Public OpenAPI snapshot exported from the Traceport API, plus its source record
fixtures/      Shared request/response cases every SDK must handle identically
conformance/   Live-server scenarios run by every SDK against a real Traceport API
scripts/       Repository tooling (contract export, validation)
typescript/    TypeScript npm workspace: packages/core, packages/workflows
go/            Go module: package traceport (client) and package workflows
python/        Python distribution traceport-ai: traceport_ai (client) and traceport_ai.workflows
```

The contract and fixtures are shared. A behavior change lands in `contract/` or `fixtures/` first, then in each language.

## Behavior shared by all SDKs

- Authenticate with a Traceport API key (`Authorization: Bearer <key>`). SDKs are server-side libraries; never ship an API key to a browser.
- Successful responses are unwrapped from the `{data, error, status, errorCode}` envelope.
- HTTP failures raise typed errors that carry the status and `errorCode` (and a request ID when the server sends one). A workflow that ran and failed is a normal result, not an HTTP error.
- `execute` and `runs.start` always send an `Idempotency-Key`; retries of transient failures reuse the same key and body, so they return the original result instead of running twice. A timed-out `execute` is not retried, because the workflow keeps running on the server.

## Contributing and security

- [CONTRIBUTING.md](./CONTRIBUTING.md): layout rules, commits, releases and CI.
- [SECURITY.md](./SECURITY.md): how to report a vulnerability privately.

## License

[Apache License 2.0](./LICENSE)
