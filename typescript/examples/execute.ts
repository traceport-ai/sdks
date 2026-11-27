/**
 * Run a workflow and wait for its result in one request.
 *
 *   TRACEPORT_API_KEY=... TRACEPORT_DEPLOYMENT=support-triage-prod npx tsx examples/execute.ts
 */

import { APIError, ConflictError, Traceport } from "@traceport/core";
import { Workflows } from "@traceport/workflows";

// A deployment code keeps working when a new version is deployed to it.
const deployment = process.env.TRACEPORT_DEPLOYMENT ?? "";

// One client for every Traceport product; each product package takes it.
const client = new Traceport();
const workflows = new Workflows(client);

try {
  const result = await workflows.execute({
    deployment,
    input: { question: "What is Traceport AI?" },
  });

  if (result.status === "succeeded") {
    console.log("output:", result.output);
  } else {
    // The workflow ran and failed. This is a result, not an exception.
    console.error("workflow failed:", result.error);
    console.error("partial output:", result.output);
  }
  console.log(`${result.steps.length} steps executed`);
} catch (error) {
  if (error instanceof ConflictError && error.existingRunId !== undefined) {
    // A request with the same idempotency key is still running; read that run instead.
    console.error("already running as run", error.existingRunId);
  } else if (error instanceof APIError) {
    console.error(`request failed: ${error.status} ${error.errorCode} ${error.message}`);
  } else {
    throw error;
  }
}
