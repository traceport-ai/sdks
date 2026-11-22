# Traceport TypeScript SDK

Official TypeScript packages for the [Traceport](https://traceport.ai) API.

> **Status: 0.1.0 pre-release, unpublished.** Local checks pass; live API verification and publication remain pending.

The SDK is modular: one shared client, and a package per product. Install only the products you use. Every product takes the same client, so you configure your API key, base URL, timeouts and retries once.

| Package                                        | Contents                                                                      |
| ---------------------------------------------- | ----------------------------------------------------------------------------- |
| [`@traceport/core`](./packages/core)           | The `Traceport` client, request options, error classes, retries and timeouts. |
| [`@traceport/workflows`](./packages/workflows) | Execute saved workflows and manage durable runs. Needs `@traceport/core`.     |

Document parsing will ship as `@traceport/documents`, taking the same client.

## Quick start

```ts
import { Traceport } from "@traceport/core";
import { Workflows } from "@traceport/workflows";

const client = new Traceport(); // reads TRACEPORT_API_KEY
const workflows = new Workflows(client);

const result = await workflows.execute({
  versionId: "<workflow-version-id>",
  input: { question: "What is Traceport?" },
});
```

Adding another product later reuses the same `client`; no second client or configuration.

To give one product different settings, derive a client. It keeps the credentials and base URL:

```ts
const workflows = new Workflows(client.withOptions({ timeout: 300_000, maxRetries: 5 }));
```

## Install

The packages are not on npm yet. Build and pack them from a checkout:

```sh
# From sdks/typescript/
npm ci
npm run build
npm pack --workspaces

# From your application:
npm install /absolute/path/to/traceport-core-0.1.0.tgz /absolute/path/to/traceport-workflows-0.1.0.tgz
```

After publication: `npm install @traceport/core @traceport/workflows`. Add each further product package next to `@traceport/core`; there is no all-in-one package.

`@traceport/workflows` declares `@traceport/core` as a peer dependency, so an application always has a single copy of the client and error classes. If a product reports "expected a Traceport client", run `npm ls @traceport/core` and remove the duplicate version.

## Examples

[`examples/`](./examples) covers execute, durable runs and an opt-in live conformance check. They type-check against the package sources. To run one, build first; `.ts` files run directly on Node.js 22.18+:

```sh
# From typescript/, after npm ci:
npm run build
export TRACEPORT_API_KEY="<sandbox-key>"
export TRACEPORT_BASE_URL="http://localhost:1010/v1"
export TRACEPORT_VERSION_OK="<successful-published-version-id>"
export TRACEPORT_VERSION_FAIL="<deliberately-failing-published-version-id>"
node examples/live-check.ts
```

Live examples execute real workflows and consume organization usage.

## Development

This folder is an npm workspace. Run from `typescript/` in a full checkout of the SDK repository, which supplies the shared contract, fixtures and license:

```bash
npm ci
npm run typecheck      # all packages, tests and configs, against sources
npm run lint
npm test               # unit tests, shared fixtures, contract checks
npm run build          # core, then workflows
npm run smoke          # loads the built packages in ESM and CommonJS
npm run check:package  # publint and attw for every package
npm run examples
```

Each package has its own version, `CHANGELOG.md` and release tag (`typescript/core/v0.1.0`, `typescript/workflows/v0.1.0`). Product packages import shared building blocks from `@traceport/core/internal`, which is not public API and not covered by semantic versioning.

## License

[Apache License 2.0](https://github.com/traceport-ai/sdks/blob/main/LICENSE)
