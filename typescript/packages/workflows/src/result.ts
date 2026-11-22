/**
 * Interprets stored workflow output.
 *
 * The rules match the Traceport dashboard, so the SDK and the dashboard always agree on whether a
 * workflow succeeded and what it returned:
 *  - a non-empty `error` means the workflow failed, even though the HTTP status was 200;
 *  - the output is `data.final` when it has entries, otherwise the whole `data` map.
 */

import { InvalidResponseError } from "@traceport/core";
import { WorkflowFailedError } from "./errors.js";
import { isRecord } from "@traceport/core/internal";
import type { WorkflowResult, WorkflowRun, WorkflowStep } from "./types.js";

/** Converts the server's workflow data (`{ data, error, steps }`) into a {@link WorkflowResult}. */
export function parseWorkflowResult(value: unknown, status = 200): WorkflowResult {
  if (!isRecord(value) || !isRecord(value.data)) {
    throw new InvalidResponseError("response does not contain a workflow result", status, value);
  }
  const data = value.data;
  const steps = Array.isArray(value.steps) ? (value.steps as WorkflowStep[]) : [];
  const final = data.final;
  const output = isRecord(final) && Object.keys(final).length > 0 ? final : data;
  const error = typeof value.error === "string" ? value.error.trim() : "";
  return error === ""
    ? { status: "succeeded", output, data, steps }
    : { status: "failed", output, error, data, steps };
}

/**
 * Returns the output of a successful workflow, or throws {@link WorkflowFailedError}.
 *
 * Accepts the result of `workflows.execute` or a run from `workflows.runs.get` /
 * `runs.waitForCompletion`. Throws when the workflow failed, when the run has not succeeded
 * (including runs still `queued` or `running`), and for run summaries from `runs.list`, which carry
 * no output. Pass `decode` (for example a schema parser) to validate and type the output.
 *
 * @example
 * const result = await workflows.execute({ versionId, input });
 * const output = requireOutput(result, (value) => AnswerSchema.parse(value));
 */
export function requireOutput<T = unknown>(
  target: WorkflowResult | WorkflowRun,
  decode?: (output: unknown) => T,
): T {
  const finish = (output: unknown): T => (decode ? decode(output) : (output as T));

  if (!isRun(target)) {
    if (target.status === "succeeded") return finish(target.output);
    throw new WorkflowFailedError(target.error ?? "workflow failed", {
      status: "failed",
      result: target,
    });
  }

  if (target.status === "succeeded" && target.result?.status === "succeeded") {
    return finish(target.result.output);
  }
  const message =
    target.error ??
    target.result?.error ??
    (target.status === "succeeded"
      ? `run ${target.id} has no output; read it with runs.get`
      : `run ${target.id} is ${target.status}`);
  throw new WorkflowFailedError(message, {
    runId: target.id,
    status: target.status,
    result: target.result,
  });
}

function isRun(target: WorkflowResult | WorkflowRun): target is WorkflowRun {
  return "id" in target && "configVersionID" in target;
}
