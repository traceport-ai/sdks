# Security policy

## Reporting a vulnerability

Do not open a public issue, discussion or pull request for a security problem.

Report it privately through GitHub: open this repository's **Security** tab and choose **Report a vulnerability**. Include the affected SDK and version, steps to reproduce and the impact you observed. Only the maintainers can see the report.

This covers the SDKs in this repository and the Traceport APIs they call.

## Supported versions

Every SDK is at `0.0.x`. Only the latest release of each SDK receives security fixes, so upgrade to the newest version to get a fix. A fix always ships as a new version; published versions are never changed.

## Official packages

Install Traceport SDKs only under these names:

| Language   | Package                                                                  |
| ---------- | ------------------------------------------------------------------------ |
| TypeScript | `@traceport/core` and `@traceport/workflows` on npm                      |
| Go         | `github.com/traceport-ai/sdks/go`                                        |
| Python     | `traceport-ai` on PyPI (import `traceport_ai`)                           |

The PyPI package named `traceport` (without `-ai`) is an unrelated project and is not published by Traceport.

Every release comes from a tag on `main` in this repository. npm and PyPI packages are published by this repository's GitHub Actions, except the first TypeScript `0.0.1` packages, which a maintainer published before automated publishing was set up.

## Handling credentials

- Never include a real API key, organization ID or customer data in an issue, fixture, example or log.
- Traceport API keys belong on servers. The SDKs are not designed to run in a browser with a key.
- If a key is exposed, delete it in the Traceport dashboard and create a new one.
