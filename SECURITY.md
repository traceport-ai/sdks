# Security policy

## Reporting a vulnerability

Do not open a public issue, discussion or pull request for a security problem.

Report it privately through GitHub: open this repository's **Security** tab and choose **Report a vulnerability**. Include the affected SDK and version, steps to reproduce and the impact you observed.

This covers the SDKs in this repository and the Traceport APIs they call. Reports about the API are forwarded to the team that owns it.

## Supported versions

No SDK has been released yet. After the first release, only the latest minor version of each SDK receives security fixes.

## Handling credentials

- Never include a real API key, organization ID or customer data in an issue, fixture, example or log.
- Traceport API keys belong on servers. The SDKs are not designed to run in a browser with a key.
