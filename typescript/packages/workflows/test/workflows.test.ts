/**
 * Workflow resources: argument mapping, polling and result helpers.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { APITimeoutError, InvalidResponseError, NotFoundError } from "@traceport/core";
import {
  WaitTimeoutError,
  WorkflowFailedError,
  requireOutput,
  type WorkflowResult,
  type WorkflowRun,
  type WaitForCompletionOptions,
} from "../src/index.js";
import {
  envelope,
  errorEnvelope,
  jsonResponse,
  stalledResponse,
  testClient,
} from "../../../test-utils/helpers.js";

const VERSION_ID = "00000000-0000-4000-8000-000000000001";
const RUN_ID = "00000000-0000-4000-8000-000000000002";

function run(status: WorkflowRun["status"], extra: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: RUN_ID,
    configVersionID: VERSION_ID,
    revision: 1,
    status,
    mode: "production",
    source: "api_async",
    createdAt: "2026-11-12T10:00:00Z",
    ...extra,
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("argument validation", () => {
  const { workflows, requests } = testClient([]);

  it("requires a versionId", async () => {
    await expect(workflows.execute({ versionId: "" })).rejects.toBeInstanceOf(TypeError);
  });

  it("requires input to be an object", async () => {
    await expect(
      workflows.runs.start({
        versionId: VERSION_ID,
        input: [] as unknown as Record<string, unknown>,
      }),
    ).rejects.toBeInstanceOf(TypeError);
  });

  it.each([["has space"], ["x".repeat(201)], [""], ["tab\there"]])(
    "rejects idempotency key %j",
    async (key) => {
      await expect(
        workflows.runs.start({ versionId: VERSION_ID }, { idempotencyKey: key }),
      ).rejects.toBeInstanceOf(TypeError);
    },
  );

  it("requires a runId", async () => {
    await expect(workflows.runs.get(" ")).rejects.toBeInstanceOf(TypeError);
    expect(requests).toHaveLength(0);
  });
});

describe("runs.list", () => {
  it("omits unset filters", async () => {
    const { workflows, requests } = testClient([envelope({ items: [], limit: 50, offset: 0 })]);
    await workflows.runs.list();
    expect([...requests[0]!.url.searchParams.keys()]).toEqual([]);
  });
});

describe("run response validation", () => {
  describe.each(["start", "get", "list"] as const)("runs.%s", (method) => {
    it.each([null, {}, [], 123, "invalid"])("rejects malformed run %j", async (value) => {
      const data = method === "list" ? { items: [value], limit: 50, offset: 0 } : value;
      const status = method === "start" ? 202 : 200;
      const { workflows, requests } = testClient([envelope(data, status)], { maxRetries: 2 });
      const pending =
        method === "start"
          ? workflows.runs.start({ versionId: VERSION_ID })
          : method === "get"
            ? workflows.runs.get(RUN_ID)
            : workflows.runs.list();
      const error: unknown = await pending.catch((caught: unknown) => caught);
      expect(error).toBeInstanceOf(InvalidResponseError);
      expect(error).toMatchObject({ status, body: value });
      expect(requests).toHaveLength(1);
    });
  });

  it.each([
    ["id", ""],
    ["configVersionID", undefined],
    ["revision", "1"],
    ["revision", -1],
    ["revision", 1.5],
    ["status", "unknown"],
    ["mode", "unknown"],
    ["source", undefined],
    ["createdAt", 123],
  ])("rejects invalid required field %s = %j", async (key, value) => {
    const { workflows } = testClient([envelope({ ...run("queued"), [key]: value })]);
    await expect(workflows.runs.get(RUN_ID)).rejects.toBeInstanceOf(InvalidResponseError);
  });

  it("preserves additive fields and unrecognized stored output", async () => {
    const output = { futureShape: true };
    const { workflows } = testClient([
      envelope({ ...run("succeeded", { output }), extraField: 42 }),
    ]);
    const result = await workflows.runs.get(RUN_ID);
    expect(result).toMatchObject({ extraField: 42, output });
    expect(result.result).toBeUndefined();
  });
});

describe("runs.waitForCompletion", () => {
  it.each(
    (["timeout", "pollInterval", "maxPollInterval", "requestTimeout"] as const).flatMap((key) =>
      [0, -1, Number.NaN, Infinity, 2 ** 31].map((value) => ({ [key]: value })),
    ),
  )("rejects invalid polling settings before sending: %j", async (options) => {
    const { workflows, requests } = testClient([]);
    await expect(
      workflows.runs.waitForCompletion(RUN_ID, options as WaitForCompletionOptions),
    ).rejects.toBeInstanceOf(TypeError);
    expect(requests).toHaveLength(0);
  });

  it.each([-1, 1.5, Number.NaN, Infinity])("rejects invalid maxRetries %j", async (maxRetries) => {
    const { workflows, requests } = testClient([]);
    await expect(workflows.runs.waitForCompletion(RUN_ID, { maxRetries })).rejects.toBeInstanceOf(
      TypeError,
    );
    expect(requests).toHaveLength(0);
  });

  it("bounds the first request and reports no last run when it never finishes", async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | undefined;
    const { workflows, requests } = testClient([
      (_request, fetchSignal) => {
        signal = fetchSignal;
        return Promise.resolve(stalledResponse(fetchSignal));
      },
    ]);
    const pending = workflows.runs
      .waitForCompletion(RUN_ID, { timeout: 100, requestTimeout: 5_000 })
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(100);
    const error = await pending;
    expect(error).toBeInstanceOf(WaitTimeoutError);
    expect(error).toMatchObject({ runId: RUN_ID, lastRun: undefined });
    expect(signal?.aborted).toBe(true);
    expect(requests).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not start another poll at the deadline", async () => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient([
      envelope(run("running")),
      envelope(run("succeeded")),
    ]);
    const pending = workflows.runs
      .waitForCompletion(RUN_ID, { timeout: 100, pollInterval: 500 })
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(100);
    expect(await pending).toMatchObject({ name: "WaitTimeoutError", lastRun: run("running") });
    expect(requests).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("bounds Retry-After backoff and retains the last observed run", async () => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient(
      [
        envelope(run("running")),
        { ...errorEnvelope(503, "unavailable"), headers: { "Retry-After": "60" } },
        envelope(run("succeeded")),
      ],
      { maxRetries: 2 },
    );
    const pending = workflows.runs
      .waitForCompletion(RUN_ID, { timeout: 500, pollInterval: 100 })
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(500);
    expect(await pending).toMatchObject({ name: "WaitTimeoutError", lastRun: run("running") });
    expect(requests).toHaveLength(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("rejects a late terminal response even when custom fetch ignores cancellation", async () => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient([
      () =>
        new Promise((resolve) => {
          setTimeout(() => {
            resolve(jsonResponse(envelope(run("succeeded"))));
          }, 200);
        }),
    ]);
    const pending = workflows.runs
      .waitForCompletion(RUN_ID, { timeout: 100 })
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(100);
    expect(await pending).toBeInstanceOf(WaitTimeoutError);
    await vi.advanceTimersByTimeAsync(100);
    expect(requests).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps caller cancellation distinct from observation timeout", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const reason = new Error("stop observing");
    const { workflows, requests } = testClient([
      (_request, signal) => Promise.resolve(stalledResponse(signal)),
    ]);
    const pending = workflows.runs
      .waitForCompletion(RUN_ID, { signal: controller.signal, timeout: 100 })
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(0);
    controller.abort(reason);
    expect(await pending).toMatchObject({ name: "RequestAbortedError", cause: reason });
    expect(requests).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("rejects an already aborted signal before polling", async () => {
    const { workflows, requests } = testClient([]);
    await expect(
      workflows.runs.waitForCompletion(RUN_ID, { signal: AbortSignal.abort() }),
    ).rejects.toMatchObject({ name: "RequestAbortedError" });
    expect(requests).toHaveLength(0);
  });

  it("preserves a shorter per-request timeout", async () => {
    vi.useFakeTimers();
    const { workflows } = testClient([
      (_request, signal) => Promise.resolve(stalledResponse(signal)),
    ]);
    const pending = workflows.runs
      .waitForCompletion(RUN_ID, { timeout: 100, requestTimeout: 20, maxRetries: 0 })
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(20);
    expect(await pending).toBeInstanceOf(APITimeoutError);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("caps the first polling interval at maxPollInterval", async () => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient([
      envelope(run("running")),
      envelope(run("succeeded")),
    ]);
    const pending = workflows.runs.waitForCompletion(RUN_ID, {
      timeout: 100,
      pollInterval: 500,
      maxPollInterval: 10,
    });
    await vi.advanceTimersByTimeAsync(10);
    await expect(pending).resolves.toMatchObject({ status: "succeeded" });
    expect(requests).toHaveLength(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("polls until the run reaches a terminal status", async () => {
    vi.useFakeTimers();
    const output = { data: { final: { answer: 42 } }, error: "", steps: [] };
    const { workflows, requests } = testClient([
      envelope(run("queued")),
      envelope(run("running")),
      envelope(run("succeeded", { output })),
    ]);
    const pending = workflows.runs.waitForCompletion(RUN_ID, { pollInterval: 100 });
    await vi.runAllTimersAsync();

    const finished = await pending;
    expect(finished.status).toBe("succeeded");
    expect(finished.result?.output).toEqual({ answer: 42 });
    expect(requests).toHaveLength(3);
  });

  it("returns failed and interrupted runs instead of throwing", async () => {
    const { workflows } = testClient([envelope(run("interrupted"))]);
    await expect(workflows.runs.waitForCompletion(RUN_ID)).resolves.toMatchObject({
      status: "interrupted",
    });
  });

  it("throws WaitTimeoutError with the last state when the timeout passes", async () => {
    vi.useFakeTimers();
    const { workflows } = testClient(Array.from({ length: 20 }, () => envelope(run("running"))));
    const pending = workflows.runs
      .waitForCompletion(RUN_ID, { timeout: 3_000, pollInterval: 1_000 })
      .catch((e: unknown) => e);
    await vi.runAllTimersAsync();

    const error = await pending;
    expect(error).toBeInstanceOf(WaitTimeoutError);
    expect((error as WaitTimeoutError).runId).toBe(RUN_ID);
    expect((error as WaitTimeoutError).lastRun?.status).toBe("running");
  });

  it("surfaces request errors", async () => {
    const { workflows } = testClient([
      errorEnvelope(404, "workflow run not found", "workflow_run_not_found"),
    ]);
    await expect(workflows.runs.waitForCompletion(RUN_ID)).rejects.toBeInstanceOf(NotFoundError);
  });
});

describe("requireOutput", () => {
  const succeeded: WorkflowResult = { status: "succeeded", output: { a: 1 }, data: {}, steps: [] };
  const failed: WorkflowResult = {
    status: "failed",
    output: { partial: true },
    error: "boom",
    data: {},
    steps: [],
  };

  it("returns the output of a successful result", () => {
    expect(requireOutput(succeeded)).toEqual({ a: 1 });
  });

  it("applies a decoder", () => {
    expect(requireOutput(succeeded, (value) => (value as { a: number }).a)).toBe(1);
  });

  it("throws WorkflowFailedError with the partial result", () => {
    const error = (() => {
      try {
        requireOutput(failed);
      } catch (e) {
        return e;
      }
      return undefined;
    })();
    expect(error).toBeInstanceOf(WorkflowFailedError);
    expect((error as WorkflowFailedError).message).toBe("boom");
    expect((error as WorkflowFailedError).result?.output).toEqual({ partial: true });
  });

  it("returns the output of a succeeded run", () => {
    expect(requireOutput(run("succeeded", { result: succeeded }))).toEqual({ a: 1 });
  });

  it("throws for runs that did not succeed, including unfinished ones", () => {
    expect(() => requireOutput(run("failed", { error: "boom", result: failed }))).toThrow(
      WorkflowFailedError,
    );
    expect(() => requireOutput(run("running"))).toThrow(/is running/);
  });

  it("throws for a succeeded run summary without output", () => {
    expect(() => requireOutput(run("succeeded"))).toThrow(/has no output/);
  });
});
