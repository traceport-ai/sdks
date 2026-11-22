/**
 * Start a durable run, store its ID, then wait for it with a bounded timeout.
 *
 *   TRACEPORT_API_KEY=... TRACEPORT_VERSION_ID=... npx tsx examples/start-and-wait.ts
 */

import { randomUUID } from "node:crypto";
import { Traceport } from "@traceport/core";
import {
  WaitTimeoutError,
  WorkflowFailedError,
  Workflows,
  requireOutput,
} from "@traceport/workflows";

const versionId = process.env.TRACEPORT_VERSION_ID ?? "";
const workflows = new Workflows(new Traceport());

// Use one key per logical start and persist it with your job. Retrying with the same key and input
// returns the original run instead of starting a second one.
const idempotencyKey = randomUUID();

const run = await workflows.runs.start(
  { versionId, input: { question: "What is Traceport?" } },
  { idempotencyKey },
);
console.log("started run", run.id, run.status);

try {
  const finished = await workflows.runs.waitForCompletion(run.id, { timeout: 120_000 });
  console.log("output:", requireOutput(finished));
} catch (error) {
  if (error instanceof WaitTimeoutError) {
    // Only the wait stopped; the run keeps going. Check again later with runs.get(run.id).
    console.log("observation timed out; last status:", error.lastRun?.status ?? "not yet observed");
  } else if (error instanceof WorkflowFailedError) {
    console.error(`run ${error.runId ?? ""} ${error.status}: ${error.message}`);
  } else {
    throw error;
  }
}

// Recent runs of this version, newest first.
const page = await workflows.runs.list({ versionId, limit: 5 });
for (const item of page.items) console.log(item.id, item.status, item.createdAt);
