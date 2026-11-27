/**
 * Workflows product for the Traceport TypeScript SDK.
 *
 * Takes the shared client from `@traceport/core`:
 *
 * @example
 * import { Traceport } from "@traceport/core";
 * import { Workflows } from "@traceport/workflows";
 *
 * const workflows = new Workflows(new Traceport());
 * const result = await workflows.execute({ versionId, input: { question: "Hi" } });
 *
 * @packageDocumentation
 */

export { Workflows } from "./workflows.js";
export { Runs, type WaitForCompletionOptions } from "./runs.js";
export { requireOutput } from "./result.js";
export { WaitTimeoutError, WorkflowFailedError } from "./errors.js";
export type {
  ListWorkflowRunsParams,
  TerminalWorkflowRunStatus,
  WorkflowResult,
  WorkflowRun,
  WorkflowRunBilling,
  WorkflowRunMode,
  WorkflowRunPage,
  WorkflowRunStatus,
  WorkflowStartParams,
  WorkflowStartByDeployment,
  WorkflowStartByVersion,
  WorkflowStep,
} from "./types.js";
