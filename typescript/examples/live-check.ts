/**
 * Live check against a running Traceport API (roadmap SDK-07 / conformance C-01 to C-08).
 *
 * Needs two active workflow versions: one that succeeds and one that fails on purpose.
 * Each run consumes workflow executions on the key's organization (about 9 per full pass).
 *
 *   TRACEPORT_API_KEY=... \
 *   TRACEPORT_BASE_URL=http://localhost:1010/v1 \
 *   TRACEPORT_VERSION_OK=<active version that succeeds> \
 *   TRACEPORT_VERSION_FAIL=<active version that fails> \
 *   node examples/live-check.ts
 */

import { randomUUID } from "node:crypto";
import {
  APITimeoutError,
  AuthenticationError,
  ConflictError,
  NotFoundError,
  Traceport,
} from "@traceport/core";
import { WaitTimeoutError, Workflows, requireOutput } from "@traceport/workflows";

const okVersion = requiredEnv("TRACEPORT_VERSION_OK");
const failVersion = requiredEnv("TRACEPORT_VERSION_FAIL");
const workflows = new Workflows(new Traceport());
const input = { question: "SDK live check" };
let failures = 0;

/** Runs one scenario and prints PASS, FAIL or SKIP with details. */
async function check(id: string, name: string, scenario: () => Promise<string>): Promise<void> {
  try {
    const detail = await scenario();
    const skipped = detail.startsWith("SKIP");
    console.log(`${skipped ? "SKIP" : "PASS"}  ${id} ${name}${detail ? ` - ${detail}` : ""}`);
  } catch (error) {
    failures++;
    console.log(`FAIL  ${id} ${name} - ${describe(error)}`);
  }
}

/** Throws when `condition` is false, so the scenario is reported as FAIL. */
function assert(condition: boolean, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

/** Expects `promise` to reject with an instance of `type`, and returns that error. */
async function expectError<E extends Error>(
  promise: Promise<unknown>,
  type: abstract new (...args: never[]) => E,
): Promise<E> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof type) return error;
    throw new Error(`expected ${type.name}, got ${describe(error)}`, { cause: error });
  }
  throw new Error(`expected ${type.name}, but the call succeeded`);
}

await check("C-01", "execute a successful workflow", async () => {
  const result = await workflows.execute({ versionId: okVersion, input });
  assert(result.status === "succeeded", `status ${result.status}: ${result.error ?? ""}`);
  return `${result.steps.length} steps, output ${JSON.stringify(result.output)}`;
});

await check("C-02", "execute a failing workflow returns a failed result", async () => {
  const result = await workflows.execute({ versionId: failVersion, input });
  assert(result.status === "failed", "expected status failed");
  assert(result.error !== undefined && result.error !== "", "expected an error message");
  return `error "${result.error}", partial output keys ${Object.keys(result.data).join(",")}`;
});

await check("C-03", "invalid API key raises AuthenticationError", async () => {
  const badWorkflows = new Workflows(
    new Traceport({ apiKey: "invalid-key-for-sdk-check", maxRetries: 0 }),
  );
  const error = await expectError(badWorkflows.runs.list({ limit: 1 }), AuthenticationError);
  return `status ${error.status}, errorCode "${error.errorCode}"`;
});

await check("C-03b", "unknown version raises NotFoundError", async () => {
  const error = await expectError(
    workflows.runs.start({ versionId: randomUUID(), input }),
    NotFoundError,
  );
  return `errorCode "${error.errorCode}"`;
});

const startKey = randomUUID();
let startedRunId = "";

await check("C-04", "start a run and wait for completion", async () => {
  const run = await workflows.runs.start(
    { versionId: okVersion, input },
    { idempotencyKey: startKey },
  );
  startedRunId = run.id;
  const finished = await workflows.runs.waitForCompletion(run.id, { timeout: 120_000 });
  assert(finished.id === run.id, "run ID changed");
  return `run ${run.id} ${finished.status}, output ${JSON.stringify(requireOutput(finished))}`;
});

await check("C-05", "same key and input returns the original run", async () => {
  assert(startedRunId !== "", "C-04 did not start a run");
  const replay = await workflows.runs.start(
    { versionId: okVersion, input },
    { idempotencyKey: startKey },
  );
  assert(replay.id === startedRunId, `got a new run ${replay.id}`);
  return `same run ${replay.id}`;
});

await check("C-06", "same key with different input raises ConflictError", async () => {
  const error = await expectError(
    workflows.runs.start(
      { versionId: okVersion, input: { question: "different" } },
      { idempotencyKey: startKey },
    ),
    ConflictError,
  );
  return `errorCode "${error.errorCode}"`;
});

await check("C-06b", "execute replays a finished result for the same key", async () => {
  const key = randomUUID();
  const first = await workflows.execute({ versionId: okVersion, input }, { idempotencyKey: key });
  const second = await workflows.execute({ versionId: okVersion, input }, { idempotencyKey: key });
  assert(JSON.stringify(first.output) === JSON.stringify(second.output), "outputs differ");
  return "identical output";
});

await check("C-07", "observation timeout leaves the run alive", async () => {
  const run = await workflows.runs.start({ versionId: okVersion, input });
  try {
    const finished = await workflows.runs.waitForCompletion(run.id, { timeout: 1 });
    return `SKIP: run already ${finished.status} on the first poll; use a slower workflow to test`;
  } catch (error) {
    if (!(error instanceof WaitTimeoutError)) throw error;
    const later = await workflows.runs.waitForCompletion(run.id, { timeout: 120_000 });
    return `timed out at ${error.lastRun?.status ?? "no status received"}, later ${later.status}`;
  }
});

await check("C-07b", "execute request timeout raises APITimeoutError", async () => {
  // The workflow may still run (and count) on the server; only the request stops waiting.
  await expectError(
    workflows.execute({ versionId: okVersion, input }, { timeout: 1 }),
    APITimeoutError,
  );
  return "";
});

await check("C-08", "list runs filtered by version", async () => {
  const page = await workflows.runs.list({ versionId: okVersion, limit: 10 });
  assert(page.items.length > 0, "no runs listed");
  assert(
    page.items.every((item) => item.configVersionID === okVersion),
    "filter not applied",
  );
  assert(
    page.items.every((item) => item.output === undefined),
    "summaries should not include output",
  );
  return `${page.items.length} runs, newest ${page.items[0]?.status ?? ""}`;
});

console.log(failures === 0 ? "\nAll checks passed." : `\n${failures} check(s) failed.`);
process.exitCode = failures === 0 ? 0 : 1;

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (value === undefined || value === "") throw new Error(`set ${name}`);
  return value;
}

function describe(error: unknown): string {
  if (error instanceof Error) {
    const code = "errorCode" in error ? ` [${String(error.errorCode)}]` : "";
    return `${error.name}: ${error.message}${code}`;
  }
  return String(error);
}
