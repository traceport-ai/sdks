/**
 * `workflows.runs`: durable workflow runs.
 *
 * A run is started once, executes in the background on the server, and is read back by ID.
 * Starting is idempotent: the SDK always sends an `Idempotency-Key`, and retrying with the same key
 * and input returns the original run instead of starting a new one.
 */

import { InvalidResponseError, RequestAbortedError } from "@traceport/core";
import { WaitTimeoutError } from "./errors.js";
import { isRecord, sleep } from "@traceport/core/internal";
import type { MutationRequestOptions, RequestOptions } from "@traceport/core";
import type { Traceport } from "@traceport/core";
import {
  transportOf,
  validateMaxRetries,
  validateTimeout,
  type Transport,
} from "@traceport/core/internal";
import { parseWorkflowResult } from "./result.js";
import type {
  ListWorkflowRunsParams,
  TerminalWorkflowRunStatus,
  WorkflowRun,
  WorkflowRunPage,
  WorkflowStartParams,
} from "./types.js";
import { requireId, startBody, resolveIdempotencyKey } from "./validation.js";

/** Options for the `waitForCompletion` instance method on {@link Runs}. */
export interface WaitForCompletionOptions extends Omit<RequestOptions, "timeout"> {
  /** How long to observe the run before throwing {@link WaitTimeoutError}, in ms. Default 10 minutes. */
  timeout?: number;
  /** Delay before the second poll, in ms. Later polls back off up to `maxPollInterval`. Default 1000. */
  pollInterval?: number;
  /** Longest delay between polls, in ms. Default 5000. */
  maxPollInterval?: number;
  /** Timeout for each individual `runs.get` request, in ms. Defaults to the client timeout. */
  requestTimeout?: number;
}

const TERMINAL_STATUSES: ReadonlySet<string> = new Set<TerminalWorkflowRunStatus>([
  "succeeded",
  "failed",
  "interrupted",
]);

const DEFAULT_WAIT_TIMEOUT_MS = 10 * 60_000;
const DEFAULT_POLL_INTERVAL_MS = 1_000;
const DEFAULT_MAX_POLL_INTERVAL_MS = 5_000;
const POLL_BACKOFF_FACTOR = 1.5;
const WAIT_TIMEOUT_REASON = Symbol("traceport.waitTimeout");
const RUN_STATUSES: ReadonlySet<string> = new Set(["queued", "running", ...TERMINAL_STATUSES]);

/** Durable workflow runs. Access through `workflows.runs`. */
export class Runs {
  // An ES private field keeps the internal Transport type out of the published declarations.
  readonly #transport: Transport;

  /**
   * Usually reached as `workflows.runs`. Constructing `Runs` directly with a client is equivalent.
   *
   * @throws {TypeError} `client` is not a Traceport client from `@traceport/core`.
   */
  constructor(client: Traceport) {
    this.#transport = transportOf(client);
  }

  /**
   * Starts a workflow run in the background and returns it immediately (usually `queued`).
   *
   * Store the returned `id` and read it later with {@link get} or {@link waitForCompletion}.
   * The request is retried automatically with the same idempotency key; a retry after the first
   * attempt succeeded returns the original run.
   *
   * @throws {NotFoundError} The version does not exist or belongs to another organization.
   * @throws {ConflictError} The idempotency key was already used with a different input.
   * @throws {PaymentRequiredError | PermissionDeniedError} Billing or plan limits block the run.
   */
  async start(params: WorkflowStartParams, options?: MutationRequestOptions): Promise<WorkflowRun> {
    const response = await this.#transport.request<unknown>({
      method: "POST",
      path: "/workflow/runs",
      body: startBody(params),
      idempotencyKey: resolveIdempotencyKey(options?.idempotencyKey),
      // Starting only records the run, so a timed-out attempt is safe to retry: the server either
      // never saw it or returns the original run for the same key.
      retryOnTimeout: true,
      options,
    });
    return toRun(response.data, response.status);
  }

  /**
   * Reads a run. A failed or interrupted run is returned normally, not thrown; check `status`,
   * or use `requireOutput(run)` to throw on anything but success.
   *
   * @throws {NotFoundError} The run does not exist or belongs to another organization.
   */
  async get(runId: string, options?: RequestOptions): Promise<WorkflowRun> {
    const id = requireId(runId, "runId");
    const response = await this.#transport.request<unknown>({
      method: "GET",
      path: `/workflow/runs/${encodeURIComponent(id)}`,
      retryOnTimeout: true,
      options,
    });
    return toRun(response.data, response.status);
  }

  /** Lists runs, newest first. Summaries do not include `output` or `result`. */
  async list(
    params: ListWorkflowRunsParams = {},
    options?: RequestOptions,
  ): Promise<WorkflowRunPage> {
    const response = await this.#transport.request<unknown>({
      method: "GET",
      path: "/workflow/runs",
      query: {
        configVersionID: params.versionId,
        status: params.status,
        limit: params.limit,
        offset: params.offset,
      },
      retryOnTimeout: true,
      options,
    });
    const page = response.data;
    if (
      !isRecord(page) ||
      !Array.isArray(page.items) ||
      typeof page.limit !== "number" ||
      typeof page.offset !== "number"
    ) {
      throw new InvalidResponseError("response is not a run page", response.status, page);
    }
    return {
      items: page.items.map((item: unknown) => toRun(item, response.status)),
      limit: page.limit,
      offset: page.offset,
    };
  }

  /**
   * Polls a run until it reaches a terminal status (`succeeded`, `failed` or `interrupted`) and
   * returns it.
   *
   * The wait is bounded by `timeout`. When it passes, {@link WaitTimeoutError} is thrown and the run
   * keeps going on the server; nothing is cancelled. Aborting `signal` stops polling the same way.
   */
  async waitForCompletion(
    runId: string,
    options: WaitForCompletionOptions = {},
  ): Promise<WorkflowRun> {
    const id = requireId(runId, "runId");
    const timeout = options.timeout ?? DEFAULT_WAIT_TIMEOUT_MS;
    const maxInterval = options.maxPollInterval ?? DEFAULT_MAX_POLL_INTERVAL_MS;
    const pollInterval = options.pollInterval ?? DEFAULT_POLL_INTERVAL_MS;
    validateTimeout(timeout, "timeout");
    validateTimeout(maxInterval, "maxPollInterval");
    validateTimeout(pollInterval, "pollInterval");
    if (options.requestTimeout !== undefined)
      validateTimeout(options.requestTimeout, "requestTimeout");
    if (options.maxRetries !== undefined) validateMaxRetries(options.maxRetries);
    if (options.signal?.aborted) {
      throw new RequestAbortedError("request was aborted", { cause: options.signal.reason });
    }

    const deadline = Date.now() + timeout;
    let interval = Math.min(pollInterval, maxInterval);
    let lastRun: WorkflowRun | undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      controller.abort(WAIT_TIMEOUT_REASON);
    }, timeout);
    const onAbort = (): void => {
      controller.abort(options.signal?.reason);
    };
    options.signal?.addEventListener("abort", onAbort, { once: true });

    const getOptions: RequestOptions = { signal: controller.signal };
    if (options.maxRetries !== undefined) getOptions.maxRetries = options.maxRetries;
    if (options.headers !== undefined) getOptions.headers = options.headers;
    if (options.requestTimeout !== undefined) getOptions.timeout = options.requestTimeout;

    try {
      for (;;) {
        if (Date.now() >= deadline) throw new WaitTimeoutError(id, lastRun, timeout);
        const run = await this.get(id, getOptions);
        // Do not accept a response delivered after the observation deadline.
        if (Date.now() >= deadline) throw new WaitTimeoutError(id, lastRun, timeout);
        lastRun = run;
        if (TERMINAL_STATUSES.has(run.status)) return run;

        await sleep(Math.min(interval, deadline - Date.now()), controller.signal);
        interval = Math.min(interval * POLL_BACKOFF_FACTOR, maxInterval);
      }
    } catch (error) {
      if (controller.signal.reason === WAIT_TIMEOUT_REASON) {
        throw new WaitTimeoutError(id, lastRun, timeout);
      }
      throw error;
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", onAbort);
    }
  }
}

/** Adds the interpreted `result` to a run read from the API. */
function toRun(value: unknown, status: number): WorkflowRun {
  if (!isWorkflowRun(value)) {
    throw new InvalidResponseError("response is not a workflow run", status, value);
  }
  const run = value;
  if (!isRecord(run.output)) return run;
  try {
    return { ...run, result: parseWorkflowResult(run.output) };
  } catch {
    // Unrecognized stored output: keep the raw `output` and leave `result` unset rather than
    // failing a status read.
    return run;
  }
}

/** Validate required resource fields while preserving additive fields from newer servers. */
function isWorkflowRun(value: unknown): value is WorkflowRun {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    value.id.trim() !== "" &&
    typeof value.configVersionID === "string" &&
    value.configVersionID.trim() !== "" &&
    typeof value.revision === "number" &&
    Number.isInteger(value.revision) &&
    value.revision >= 0 &&
    typeof value.status === "string" &&
    RUN_STATUSES.has(value.status) &&
    (value.mode === "production" || value.mode === "draft_test") &&
    typeof value.source === "string" &&
    typeof value.createdAt === "string"
  );
}
