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
- Python: one distribution, `traceport-ai` on PyPI, imported as `traceport_ai`. `src/traceport_ai/` is core (`_client.py`, `_core/`); each product is a subpackage such as `src/traceport_ai/workflows/`. Product-specific dependencies go in an extra (`traceport-ai[documents]`). Tests are in `tests/`, with a `pyproject.toml` and a development `uv.lock`.

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
- Release tags are prefixed with the folder (and, for TypeScript, the package) name: `typescript/core/v0.0.1`, `typescript/workflows/v0.0.1`, `go/v0.0.1`, `python/v0.0.1`. Go requires the `go/` prefix to resolve module versions in a subdirectory. Go and Python version all their product packages together.
- A TypeScript product's `peerDependencies` range on `@traceport/core` must cover the core version it is tested with.
- Packages are published only from GitHub Actions through OIDC (npm provenance, PyPI trusted publishing), gated by a protected `release` environment. No long-lived registry tokens.

### Releasing a TypeScript package

`release-typescript.yml` publishes one package per tag through npm trusted publishing. The very first version of each package (`0.0.1`) was published by hand, because npm only accepts a trusted publisher on a package that already exists.

1. Bump `version` in the package's `package.json`. For `@traceport/core`, also bump `VERSION` in `packages/core/src/version.ts` and the `@traceport/core` peer and dev dependency in `packages/workflows/package.json` (`^0.0.x` ranges match one version only). Run `npm install` in `typescript/` to refresh the lockfile.
2. Add the release to the package's `CHANGELOG.md`, open a pull request and merge it into `main`.
3. Tag the merge commit on `main` and push the tag:

   ```sh
   git tag typescript/core/v0.0.2 && git push origin typescript/core/v0.0.2
   ```

4. Approve the `release` environment in the Actions run. The workflow refuses tags that are not on `main` or whose version differs from `package.json`, reruns every check, publishes, and confirms the version is live. It skips versions that are already on npm. Release core before any product that needs the new core version.

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
