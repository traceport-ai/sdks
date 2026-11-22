/**
 * Public types for the workflows product.
 *
 * Resource fields keep the API's wire names (for example `configVersionID`) so they match the
 * REST reference. Method parameters use friendlier names (`versionId`, `input`) that the SDK maps
 * to the wire fields. Workflow inputs and outputs are graph-specific, so they stay generic JSON.
 */

/** Status of a durable workflow run. */
export type WorkflowRunStatus = "queued" | "running" | "succeeded" | "failed" | "interrupted";

/** Statuses after which a run never changes again. */
export type TerminalWorkflowRunStatus = Extract<
  WorkflowRunStatus,
  "succeeded" | "failed" | "interrupted"
>;

/** How the run was started: a published version, or a dashboard test of a draft. */
export type WorkflowRunMode = "production" | "draft_test";

/** Billing receipt recorded when the run first claimed processing. */
export interface WorkflowRunBilling {
  /** How the run was paid for. */
  method: "included" | "wallet" | "invoice";
  /** UTC calendar month of the charge, for example `"2026-11"`. */
  periodMonth: string;
  currency: "USD";
  /** Amount charged, as a decimal string with four places, for example `"0.0090"`. */
  amountUsd: string;
  /** Set when a platform credit later refunded the charge (ISO 8601). */
  creditedAt?: string;
}

/** One executed node, in execution order. */
export interface WorkflowStep {
  index: number;
  nodeId: string;
  name: string;
  /** Node type, for example `"agent"` or `"end"`. */
  type: string;
  attempt: number;
  /** For example `"completed"`, `"failed"`, `"continued_after_error"` or `"limit_reached"`. */
  status: string;
  /** ISO 8601 start time. */
  startedAt?: string;
  durationMs: number;
  input?: Record<string, unknown>;
  output?: unknown;
  error?: string;
  /** Other fields the server includes (usage, dependencies, tool calls, branch IDs, …). */
  [key: string]: unknown;
}

/**
 * The interpreted result of one workflow execution.
 *
 * `status` reflects what the workflow did, not the HTTP status: a workflow that ran and failed
 * comes back with HTTP 200 and `status: "failed"`.
 */
export interface WorkflowResult {
  /** `"succeeded"` when the workflow finished without a workflow error. */
  status: "succeeded" | "failed";
  /**
   * The workflow's output: `data.final` when it has entries, otherwise the whole `data` map.
   * For a failed workflow this is the partial output produced before the failure.
   */
  output: unknown;
  /** The workflow error message. Present only when `status` is `"failed"`. */
  error?: string;
  /** Raw per-node-type results (`input`, `final`, `agent`, `router`, …). */
  data: Record<string, unknown>;
  /** Every executed node, in order. */
  steps: WorkflowStep[];
}

/** A durable workflow run. */
export interface WorkflowRun {
  id: string;
  /** The workflow version the run executes. */
  configVersionID: string;
  /** Saved revision of that version, frozen when the run started. */
  revision: number;
  status: WorkflowRunStatus;
  mode: WorkflowRunMode;
  /** Where the run came from, for example `"api_async"` or `"api_sync"`. */
  source: string;
  /** ISO 8601 creation time. */
  createdAt: string;
  /** ISO 8601 time processing started. */
  startedAt?: string;
  /** ISO 8601 time the run reached a terminal status. */
  finishedAt?: string;
  /** Run-level error message when the run failed. */
  error?: string;
  /** Where a failure came from, for example `"workflow"`, `"platform"`, `"billing"` or `"limit"`. */
  failureOrigin?: string;
  /** Billing receipt; absent until the run claims processing, and for unmetered runs. */
  billing?: WorkflowRunBilling;
  /** Raw stored workflow output. Present on single-run reads once the run finished; never in lists. */
  output?: Record<string, unknown>;
  /** {@link output} interpreted the same way as `workflows.execute`. Absent when there is no output. */
  result?: WorkflowResult;
}

/** One page of {@link WorkflowRun} summaries. Summaries never include `output` or `result`. */
export interface WorkflowRunPage {
  /** Runs, newest first. */
  items: WorkflowRun[];
  limit: number;
  offset: number;
}

/** Parameters shared by `workflows.execute` and `workflows.runs.start`. */
export interface WorkflowStartParams {
  /** ID of the active workflow version to run. Sent as `configVersionID`. */
  versionId: string;
  /** Workflow input. Sent as `additional`. Defaults to `{}`. */
  input?: Record<string, unknown>;
}

/** Filters for `workflows.runs.list`. */
export interface ListWorkflowRunsParams {
  /** Only runs of this workflow version. Sent as `configVersionID`. */
  versionId?: string;
  status?: WorkflowRunStatus;
  /** Page size, 1–100. The server default is 50. */
  limit?: number;
  /** Number of runs to skip, 0–1,000,000. */
  offset?: number;
}
