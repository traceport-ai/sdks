/**
 * Errors specific to workflows. Request failures (HTTP errors, timeouts, connection problems)
 * come from `@traceport/core` and are shared with every Traceport product.
 *
 * A workflow that runs and fails is a normal result (`status: "failed"`); it only becomes a
 * {@link WorkflowFailedError} when you opt in with `requireOutput`.
 */

import { TraceportError } from "@traceport/core";
import type { WorkflowResult, WorkflowRun } from "./types.js";

/**
 * Thrown by `requireOutput` when a workflow ran but did not succeed.
 *
 * The server request itself succeeded; this error only exists so callers can opt into
 * exception-style handling of workflow failures.
 */
export class WorkflowFailedError extends TraceportError {
  override readonly name: string = "WorkflowFailedError";
  /** Run ID, when the failure came from a durable run. */
  readonly runId: string | undefined;
  /** The run status (`"failed"`, `"interrupted"`, …) or `"failed"` for a synchronous execution. */
  readonly status: string;
  /** The workflow result with partial output and executed steps, when the server returned one. */
  readonly result: WorkflowResult | undefined;

  constructor(
    message: string,
    details: { runId?: string; status: string; result?: WorkflowResult | undefined },
  ) {
    super(message);
    this.runId = details.runId;
    this.status = details.status;
    this.result = details.result;
  }
}

/**
 * Thrown by `runs.waitForCompletion` when the observation timeout passes first.
 *
 * The run keeps going on the server; nothing is cancelled. Call `waitForCompletion` or
 * `runs.get` again later.
 */
export class WaitTimeoutError extends TraceportError {
  override readonly name: string = "WaitTimeoutError";
  /** ID of the run that was being observed. */
  readonly runId: string;
  /** The last state read before the timeout, or undefined if the first read did not finish. */
  readonly lastRun: WorkflowRun | undefined;

  constructor(runId: string, lastRun: WorkflowRun | undefined, timeoutMs: number) {
    super(
      `run ${runId} did not finish within ${timeoutMs} ms` +
        (lastRun === undefined ? " (no status received)" : ` (last status: ${lastRun.status})`),
    );
    this.runId = runId;
    this.lastRun = lastRun;
  }
}
