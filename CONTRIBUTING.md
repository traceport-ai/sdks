# Contributing

## Ground rules

1. **The API contract comes from the backend.** `contract/openapi.json` is exported from `traceport-apis` with `scripts/export_contract.py`. Never edit it by hand. See [contract/README.md](./contract/README.md).
2. **Shared behavior is defined once.** Request/response cases live in `fixtures/` and are used by every SDK's unit tests. Add or change a fixture before changing behavior in a language.
3. **Ship only working resources.** Do not add methods, types or stubs for APIs the backend does not serve yet (tasks, cancel, documents, events).
4. **Same names and semantics in every language.** Follow each language's casing conventions, but keep resource names, error classes and retry rules identical.
5. **Keep dependencies minimal.** TypeScript: no runtime dependencies. Go: standard library only. Python: `httpx` and `pydantic` only.

## Layout

Each language follows the same rule: **one shared client (core) and one module per product**. Core owns configuration, HTTP, retries, timeouts and request errors. A product module takes the core client and never creates its own HTTP layer or credentials. Core never imports a product.

- TypeScript: an npm workspace. `packages/core` (`@traceport/core`), and one package per product such as `packages/workflows` (`@traceport/workflows`, with core as a peer dependency). There is no all-in-one package: applications install core plus the products they use. Products use `@traceport/core/internal`, which is not public API. Tests live in each package's `test/`; shared test helpers in `test-utils/`.
- Go: one module. The root package `traceport` is core (public client, options, errors); each product is a package such as `workflows/`; shared infrastructure is in `internal/core/`; public-interface tests are in `test/`.
- Python: one distribution. `src/traceport/` is core (`_client.py`, `_core/`); each product is a subpackage such as `src/traceport/workflows/`. Product-specific dependencies go in an extra (`traceport[documents]`). Tests are in `tests/`, with a `pyproject.toml` and a development `uv.lock`.

To add a product, create its module in all three languages, take the core client in its constructor, and add its fixtures under `fixtures/<product>/`.

Each language folder is self-contained: its own manifest, source, tests, `examples/`, `README.md` and `CHANGELOG.md` (per package for TypeScript). Root-level folders (`contract/`, `fixtures/`, `conformance/`, `scripts/`) are shared and must not contain language-specific code.

## Commits and pull requests

Use [Conventional Commits](https://www.conventionalcommits.org/) with a scope naming the area:

```
feat(typescript): add workflows.runs.list
fix(go): honor Retry-After on 503
test(fixtures): add failed HTTP-200 execute case
chore(contract): update snapshot to traceport-apis <commit>
ci: pin actionlint
```

Scopes: `typescript`, `go`, `python`, `contract`, `fixtures`, `conformance`, `ci`, `repo`. Use a product sub-scope where helpful, for example `feat(typescript/workflows): …`.

One pull request may change the contract, fixtures and all three SDKs together when they belong to one behavior change.

## Versioning and releases

- Each SDK is versioned independently with [Semantic Versioning](https://semver.org/). All SDKs start at `0.x` until their first stable release.
- Release tags are prefixed with the folder (and, for TypeScript, the package) name: `typescript/core/v0.1.0`, `typescript/workflows/v0.1.0`, `go/v0.1.0`, `python/v0.1.0`. Go requires the `go/` prefix to resolve module versions in a subdirectory. Go and Python version all their product packages together.
- A TypeScript product's `peerDependencies` range on `@traceport/core` must cover the core version it is tested with.
- Packages are published only from GitHub Actions through OIDC (npm provenance, PyPI trusted publishing), gated by a protected `release` environment. No long-lived registry tokens.

## CI

- `repo.yml` validates the contract snapshot, fixtures and workflow files on every pull request.
- Each language gets its own workflow with path filters (for example `typescript/**`, `contract/**`, `fixtures/**`).
- Pull-request jobs never use secrets. Live conformance tests run only on `main`, on a schedule or by manual dispatch, with a dedicated sandbox API key.
- Third-party actions are pinned to a full commit SHA, with the version in a trailing comment. Dependabot keeps them current.
- Only GitHub-hosted runners are used. Never add a self-hosted runner to this public repository.

## Local checks

```bash
python3 scripts/validate_repo.py
```
