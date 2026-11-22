# Conformance

Scenarios every SDK runs against a live Traceport API, so behavior that fixtures cannot prove (timing, retries, replay) is checked end to end. TypeScript, Go, Python sync and Python async run the same list.

Conformance runs use a dedicated sandbox organization and API key with spend limits. They run only on `main`, on a schedule or by manual dispatch, never on pull requests.

| Variable | Meaning |
| --- | --- |
| `TRACEPORT_BASE_URL` | API origin, for example a local or staging server. |
| `TRACEPORT_API_KEY` | Sandbox API key. |
| `TRACEPORT_CONFORMANCE_VERSION_OK` | Active version that completes successfully. |
| `TRACEPORT_CONFORMANCE_VERSION_FAIL` | Active version that fails deliberately. |

## Scenarios

| ID | Scenario | Expected |
| --- | --- | --- |
| C-01 | `execute` a successful workflow | Final output selected; raw steps retained. |
| C-02 | `execute` a failing workflow | HTTP 200 resolved as a failed outcome, not a transport error. |
| C-03 | `execute` with an invalid key | Authentication error with status and `errorCode`, plus the request ID when the server returns one. |
| C-04 | `runs.start`, then poll `runs.get` to a terminal status | Same run ID throughout; bounded wait respects its timeout. |
| C-05 | `runs.start` twice with the same key and body | Second call returns the original run (HTTP 200). |
| C-06 | `runs.start` with the same key and a changed body | Conflict error (HTTP 409). |
| C-07 | Observation timeout on a running run | Timeout error; the run keeps going and is not cancelled. |
| C-08 | `runs.list` filtered by version and status | Newest first; limit and offset honored. |

These map to SDK-07 and LANG-04 in the implementation roadmap.
