/**
 * Runs every shared fixture (../fixtures) through the SDK. The same files drive the Go and Python
 * SDK tests, so passing here means TypeScript interprets each exchange the same way.
 */

import { describe, expect, it } from "vitest";
import * as core from "@traceport/core";
import * as products from "../src/index.js";
import type { Workflows, WorkflowResult, WorkflowRun, WorkflowRunPage } from "../src/index.js";
import { loadFixtures, testClient, type Fixture } from "../../../test-utils/helpers.js";

const fixtures = loadFixtures();

/** Calls the SDK method a fixture describes, using the fixture's request as the arguments. */
async function invoke(
  workflows: Workflows,
  fixture: Fixture,
): Promise<WorkflowResult | WorkflowRun | WorkflowRunPage> {
  const url = new URL(fixture.request.path, "https://api.test");
  // Read-only operations have no body.
  const body = fixture.request.body as
    { configVersionID: string; additional: Record<string, unknown> } | undefined;
  const key = fixture.request.headers?.["Idempotency-Key"];
  const options = key === undefined ? {} : { idempotencyKey: key };
  const params = { versionId: body?.configVersionID ?? "", input: body?.additional ?? {} };

  switch (fixture.operation) {
    case "executeWorkflow":
      return workflows.execute(params, options);
    case "startWorkflowRun":
      return workflows.runs.start(params, options);
    case "getWorkflowRun":
      return workflows.runs.get(url.pathname.split("/").at(-1)!);
    case "listWorkflowRuns": {
      const query = url.searchParams;
      const listParams: products.ListWorkflowRunsParams = {};
      if (query.has("configVersionID")) listParams.versionId = query.get("configVersionID")!;
      if (query.has("status"))
        listParams.status = query.get("status") as products.WorkflowRunStatus;
      if (query.has("limit")) listParams.limit = Number(query.get("limit"));
      if (query.has("offset")) listParams.offset = Number(query.get("offset"));
      return workflows.runs.list(listParams);
    }
  }
}

/** Compares a workflow result with a fixture's `expect.outcome`. */
function expectOutcome(
  result: WorkflowResult | undefined,
  outcome: NonNullable<Fixture["expect"]["outcome"]>,
): void {
  expect(result).toBeDefined();
  expect(result!.status).toBe(outcome.status);
  expect(result!.output).toEqual(outcome.output);
  expect(result!.error).toBe(outcome.error);
  if (outcome.stepCount !== undefined) expect(result!.steps).toHaveLength(outcome.stepCount);
}

describe("shared fixtures", () => {
  it("loads fixtures", () => {
    expect(fixtures.length).toBeGreaterThan(0);
  });

  describe.each(fixtures)("$file", (fixture) => {
    it("sends the recorded request", async () => {
      const { workflows, requests } = testClient([fixture.response]);
      await invoke(workflows, fixture).catch(() => undefined);

      expect(requests).toHaveLength(1);
      const [request] = requests;
      const expected = new URL(fixture.request.path, "https://api.test");
      expect(request!.method).toBe(fixture.request.method);
      // Fixture paths include /v1, which is part of the client's base URL.
      expect(request!.url.pathname).toBe(expected.pathname);
      expect(Object.fromEntries(request!.url.searchParams)).toEqual(
        Object.fromEntries(expected.searchParams),
      );
      expect(request!.body).toEqual(fixture.request.body);
      for (const [name, value] of Object.entries(fixture.request.headers ?? {})) {
        expect(request!.headers.get(name)).toBe(value);
      }
    });

    it(`resolves as ${fixture.expect.kind}`, async () => {
      const { workflows } = testClient([fixture.response]);
      const { kind } = fixture.expect;

      if (kind === "error") {
        const spec = fixture.expect.error!;
        const error: unknown = await invoke(workflows, fixture).then(
          () => expect.fail("expected an error"),
          (e: unknown) => e,
        );
        const ErrorClass = (
          { ...core, ...products } as unknown as Record<string, new (...args: never[]) => Error>
        )[spec.class];
        expect(ErrorClass, `SDK exports ${spec.class}`).toBeDefined();
        expect(error).toBeInstanceOf(ErrorClass);
        expect(error).toBeInstanceOf(core.APIError);
        const apiError = error as core.APIError;
        expect(apiError.name).toBe(spec.class);
        expect(apiError.status).toBe(spec.status);
        expect(apiError.errorCode).toBe(spec.errorCode);
        expect(apiError.retryable).toBe(spec.retryable);
        if (spec.existingRunId !== undefined) {
          expect((apiError as core.ConflictError).existingRunId).toBe(spec.existingRunId);
        }
        return;
      }

      const value = await invoke(workflows, fixture);
      if (kind === "outcome") {
        expectOutcome(value as WorkflowResult, fixture.expect.outcome!);
        return;
      }

      const resource = fixture.expect.resource ?? {};
      if ("itemCount" in resource) {
        const page = value as WorkflowRunPage;
        expect(page.items).toHaveLength(resource.itemCount as number);
        expect(page.limit).toBe(resource.limit);
        expect(page.offset).toBe(resource.offset);
        for (const item of page.items) expect(item.result).toBeUndefined();
        return;
      }
      expect(value).toMatchObject(resource);
      const run = value as WorkflowRun;
      if (fixture.expect.outcome) expectOutcome(run.result, fixture.expect.outcome);
      else if (run.output === undefined) expect(run.result).toBeUndefined();
    });
  });
});
