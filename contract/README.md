# Contract

The public API surface the SDKs wrap. These files are generated; do not edit `openapi.json` or `SOURCE.json` by hand.

| File                     | Purpose                                                                               |
| ------------------------ | ------------------------------------------------------------------------------------- |
| `public-operations.json` | The `operationId`s that are public. This list is the only input maintained here.      |
| `openapi.json`           | Public OpenAPI snapshot: the listed operations plus the components they reference.    |
| `SOURCE.json`            | Which `traceport-apis` commit and spec file the snapshot came from, with its SHA-256. |

## Updating the snapshot

1. Make the API change in `traceport-apis` (`internal/openapi/openapi.json`) and merge it there first.
2. From this repository, with a `traceport-apis` checkout of the merged commit:

   ```bash
   python3 scripts/export_contract.py ../traceport-apis
   python3 scripts/validate_repo.py
   ```

3. Commit the result as `chore(contract): update snapshot to traceport-apis <short-commit>`.

To expose a new operation, add its `operationId` to `public-operations.json` and re-export. Dashboard, admin and internal operations must never be listed; `validate_repo.py` rejects dashboard routes and dashboard auth schemes.

To check for drift without writing anything:

```bash
python3 scripts/export_contract.py ../traceport-apis --check
```

Public descriptions explain caller-visible behavior and exclude infrastructure
details. Repository validation rejects internal implementation terms. The workflow
contract distinguishes HTTP request errors from failed HTTP-200 workflow outcomes,
describes ordered steps and partial/final output, and preserves actual endpoint
status differences: a missing version currently returns 409 from execute and 404
from runs.start. Do not add expected status codes without checking the handler and
recorded responses. A missing request-ID header and empty errorCode are valid today.

`SOURCE.json` records uncommitted backend documentation changes honestly. Its warning
remains until those changes are committed and the snapshot is re-exported; a clean
drift check alone does not prove the backend is deployed. Recording provenance lives
on each fixture and can identify an older running contract independently.
