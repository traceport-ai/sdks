/**
 * Keeps the hand-written public types in step with contract/openapi.json.
 *
 * Each list below is checked twice: by the compiler (it must name exactly the type's keys) and at
 * runtime (it must equal the schema's properties). A field added to the API therefore fails this
 * test until the SDK type is updated.
 */

import { describe, expect, expectTypeOf, it } from "vitest";
import type {
  WorkflowRun,
  WorkflowRunBilling,
  WorkflowRunMode,
  WorkflowRunStatus,
} from "../src/index.js";
import { loadContract } from "../../../test-utils/helpers.js";

const schemas = loadContract().components.schemas;

/** Wire fields of WorkflowRun. `result` is SDK-only (derived from `output`), so it is excluded. */
const RUN_FIELDS = [
  "id",
  "configVersionID",
  "deployment",
  "revision",
  "status",
  "mode",
  "source",
  "createdAt",
  "startedAt",
  "finishedAt",
  "error",
  "failureOrigin",
  "billing",
  "output",
] as const;

const BILLING_FIELDS = ["method", "periodMonth", "currency", "amountUsd", "creditedAt"] as const;
const RUN_STATUSES = ["queued", "running", "succeeded", "failed", "interrupted"] as const;
const RUN_MODES = ["production", "draft_test"] as const;
const BILLING_METHODS = ["included", "wallet", "invoice"] as const;

const sorted = (values: readonly string[]): string[] => [...values].sort();

describe("public types match the contract", () => {
  it("WorkflowRun fields", () => {
    expectTypeOf<(typeof RUN_FIELDS)[number]>().toEqualTypeOf<
      Exclude<keyof WorkflowRun, "result">
    >();
    expect(sorted(RUN_FIELDS)).toEqual(sorted(Object.keys(schemas.WorkflowRun!.properties!)));
  });

  it("WorkflowRunBilling fields", () => {
    expectTypeOf<(typeof BILLING_FIELDS)[number]>().toEqualTypeOf<keyof WorkflowRunBilling>();
    expect(sorted(BILLING_FIELDS)).toEqual(
      sorted(Object.keys(schemas.WorkflowRunBilling!.properties!)),
    );
  });

  it("enums", () => {
    expectTypeOf<(typeof RUN_STATUSES)[number]>().toEqualTypeOf<WorkflowRunStatus>();
    expectTypeOf<(typeof RUN_MODES)[number]>().toEqualTypeOf<WorkflowRunMode>();
    expectTypeOf<(typeof BILLING_METHODS)[number]>().toEqualTypeOf<WorkflowRunBilling["method"]>();

    const run = schemas.WorkflowRun!.properties!;
    expect(sorted(RUN_STATUSES)).toEqual(sorted(run.status!.enum!));
    expect(sorted(RUN_MODES)).toEqual(sorted(run.mode!.enum!));
    expect(sorted(BILLING_METHODS)).toEqual(
      sorted(schemas.WorkflowRunBilling!.properties!.method!.enum!),
    );
  });

  it("start request fields", () => {
    expect(sorted(Object.keys(schemas.WorkflowExecuteRequest!.properties!))).toEqual(
      sorted(["configVersionID", "deployment", "additional"]),
    );
  });
});
