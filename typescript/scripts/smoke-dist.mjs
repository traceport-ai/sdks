/**
 * Smoke test for the built packages (run after `npm run build`).
 *
 * Unit tests run against sources, so they cannot see bundling mistakes. This loads the published
 * entry points through Node's own module resolution, in both ESM and CommonJS, and checks the
 * guarantees the package split depends on:
 *  - a client from @traceport/core is accepted by product packages (one shared client registry);
 *  - errors thrown by the transport are instances of the classes users import;
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const RUN_ID = "00000000-0000-4000-8000-000000000002";

/** A fetch that always answers with `status` and an envelope around `data`. */
function fetchReturning(status, data, error = "", errorCode = "") {
  return async () => new Response(JSON.stringify({ data, error, status, errorCode }), { status });
}

async function check(label, core, workflows) {
  const result = { data: { final: { ok: true } }, error: "", steps: [] };
  const client = new core.Traceport({ apiKey: "k", fetch: fetchReturning(200, result) });

  const executed = await new workflows.Workflows(client).execute({ versionId: "v" });
  assert.equal(executed.status, "succeeded", `${label}: product accepts a core client`);

  const derived = new workflows.Workflows(client.withOptions({ timeout: 5_000 }));
  assert.equal(
    (await derived.execute({ versionId: "v" })).status,
    "succeeded",
    `${label}: derived client`,
  );

  assert.throws(() => new workflows.Workflows({}), TypeError, `${label}: rejects non-clients`);

  const notFound = new workflows.Workflows(
    new core.Traceport({
      apiKey: "k",
      fetch: fetchReturning(404, null, "workflow run not found", "workflow_run_not_found"),
    }),
  );
  const error = await notFound.runs.get(RUN_ID).catch((caught) => caught);
  assert.ok(error instanceof core.NotFoundError, `${label}: NotFoundError identity`);
  assert.ok(error instanceof core.APIError, `${label}: APIError identity`);
  assert.ok(error instanceof core.TraceportError, `${label}: TraceportError identity`);

  console.log(`${label}: ok`);
}

await check("esm", await import("@traceport/core"), await import("@traceport/workflows"));
await check("cjs", require("@traceport/core"), require("@traceport/workflows"));
