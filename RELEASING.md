# Releasing

For maintainers only. Contributors open pull requests; they never bump versions, push tags or
publish packages.

## Rules

- Every SDK is versioned on its own with [Semantic Versioning](https://semver.org/) and stays at `0.x` until its first stable release.
- A release is a tag on a commit that is already on `main`. Tags are prefixed with the folder (and, for TypeScript, the package) name: `typescript/core/v0.0.2`, `typescript/workflows/v0.0.2`, `go/v0.0.2`, `python/v0.0.2`. Go requires the `go/` prefix to resolve module versions in a subdirectory. Go and Python version all their product packages together.
- Only maintainers can create release tags (tag ruleset on `typescript/**`, `go/v*` and `python/v*`).
- Packages are published only from GitHub Actions through OIDC (npm trusted publishing with provenance, PyPI trusted publishing), behind the protected `release` environment. There are no long-lived registry tokens.
- Before tagging, turn the `## Unreleased` changelog entries into the new version's heading in the same pull request as the version bump.

## TypeScript packages

`release-typescript.yml` publishes one package per tag through npm trusted publishing. The very first version of each package (`0.0.1`) was published by hand, because npm only accepts a trusted publisher on a package that already exists.

1. Bump `version` in the package's `package.json`. For `@traceport/core`, also bump `VERSION` in `packages/core/src/version.ts` and the `@traceport/core` peer and dev dependency in `packages/workflows/package.json` (`^0.0.x` ranges match one version only, and a product's peer range must cover the core version it is tested with). Run `npm install` in `typescript/` to refresh the lockfile.
2. Add the release to the package's `CHANGELOG.md`, open a pull request and merge it into `main`.
3. Tag the merge commit on `main` and push the tag:

   ```sh
   git tag typescript/core/v0.0.2 && git push origin typescript/core/v0.0.2
   ```

4. Approve the `release` environment in the Actions run. The workflow refuses tags that are not on `main` or whose version differs from `package.json`, reruns every check, publishes, and confirms the version is live. It skips versions that are already on npm. Release core before any product that needs the new core version.

## Go module

For Go, pushing the tag is the release: there is no registry upload and no approval step. The Go module proxy fetches the tag the first time anyone requests that version, and the Go checksum database then records its contents permanently. A released tag can never be moved or reused, so check everything before tagging.

1. Bump `Version` in `go/internal/core/client.go` (it is sent in the `User-Agent` header), add the release to `go/CHANGELOG.md`, open a pull request and merge it into `main` once CI passes.
2. Tag the merge commit on `main` and push the tag:

   ```sh
   git tag go/v0.0.2 && git push origin go/v0.0.2
   ```

3. `release-go.yml` checks that the tag is on `main` and matches `Version`, reruns the Go checks, asks `proxy.golang.org` for the version and installs it in a new module. pkg.go.dev lists the version within minutes.

If the workflow fails before its `announce` job, delete the tag (`git push origin :refs/tags/go/v0.0.2`) and fix the problem in a new pull request; reuse the version only if you are sure nobody fetched it. If a broken version was already fetched, release the next patch version with a `retract` directive for the broken one in `go/go.mod`. Major versions 2 and above also need the module path to end in `/v2`, `/v3` and so on.

## Python package

`release-python.yml` publishes `traceport-ai` from a `python/v<version>` tag through PyPI trusted publishing. The trusted publisher was registered on PyPI as a pending publisher before the first release, so even `0.0.1` was published by the workflow.

1. Bump `__version__` in `python/src/traceport_ai/_version.py` (use PEP 440 forms such as `0.0.2` or `0.1.0rc1`), add the release to `python/CHANGELOG.md`, open a pull request and merge it into `main`.
2. Tag the merge commit on `main` and push the tag:

   ```sh
   git tag python/v0.0.2 && git push origin python/v0.0.2
   ```

3. Approve the `release` environment in the Actions run. The `build` job refuses tags that are not on `main` or whose version differs from `__version__`, reruns every Python check and builds the wheel and sdist without publishing permissions. The `publish` job uploads exactly those files with signed attestations, and the `confirm` job installs the release from PyPI and imports it. Versions already on PyPI are skipped.

PyPI never accepts the same version twice, even after a release is deleted. If a release is broken, yank it on PyPI (installers then skip it unless it is pinned exactly) and publish the next version.
