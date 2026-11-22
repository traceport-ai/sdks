/**
 * The workflows product: run saved Traceport workflows with the shared core client.
 *
 * @example
 * import { Traceport } from "@traceport/core";
 * import { Workflows } from "@traceport/workflows";
 *
 * const client = new Traceport();
 * const workflows = new Workflows(client);
 * const result = await workflows.execute({ versionId, input: { question: "Hi" } });
 */

import type { MutationRequestOptions, Traceport } from "@traceport/core";
import { transportOf, type Transport } from "@traceport/core/internal";
import { parseWorkflowResult } from "./result.js";
import { Runs } from "./runs.js";
import type { WorkflowResult, WorkflowStartParams } from "./types.js";
import { resolveIdempotencyKey, startBody } from "./validation.js";

/**
 * The server stops a synchronous workflow after 5 minutes. Unless the call sets its own `timeout`,
 * execute waits at least this long (or the client timeout, if larger), leaving room for that budget
 * plus network and response time.
 */
const EXECUTE_MINIMUM_TIMEOUT_MS = 6 * 60_000;

/** Workflow operations. Create one with the shared {@link Traceport} client. */
export class Workflows {
  /** Durable runs: start in the background, then read or wait. */
  readonly runs: Runs;
  // An ES private field keeps the internal Transport type out of the published declarations.
  readonly #transport: Transport;

  /**
   * @param client The core Traceport client. Its credentials, base URL, timeouts and retries are
   *   used for every workflow call; no second client or configuration is needed. Use
   *   `client.withOptions(...)` to give workflows different timeouts or retries.
   * @throws {TypeError} `client` is not a Traceport client from `@traceport/core`.
   */
  constructor(client: Traceport) {
    this.#transport = transportOf(client);
    this.runs = new Runs(client);
  }

  /**
   * Runs a workflow and waits for its result in the same request.
   *
   * A workflow that runs and fails resolves normally with `status: "failed"`, its error message and
   * any partial output. Only request problems throw. Use `requireOutput(result)` to throw
   * {@link WorkflowFailedError} on a failed workflow instead.
   *
   * The SDK sends an idempotency key and retries connection failures and transient server errors
   * with it; a retry returns the stored result rather than running the workflow again. A request
   * timeout is not retried, because the server keeps running the workflow. For long workflows,
   * prefer `workflows.runs.start` and `runs.waitForCompletion`.
   *
   * @throws {ConflictError} A request with the same idempotency key is still running
   *   (`existingRunId` is set), or the key was used with a different input.
   * @throws {PaymentRequiredError | PermissionDeniedError} Billing or plan limits block the run.
   * @throws {APITimeoutError} No response within the timeout (by default the larger of 6 minutes
   *   and the client timeout).
   */
  async execute(
    params: WorkflowStartParams,
    options?: MutationRequestOptions,
  ): Promise<WorkflowResult> {
    const response = await this.#transport.request<unknown>({
      method: "POST",
      path: "/workflow/execute",
      body: startBody(params),
      idempotencyKey: resolveIdempotencyKey(options?.idempotencyKey),
      retryOnTimeout: false,
      minimumTimeout: EXECUTE_MINIMUM_TIMEOUT_MS,
      options,
    });
    return parseWorkflowResult(response.data, response.status);
  }
}
