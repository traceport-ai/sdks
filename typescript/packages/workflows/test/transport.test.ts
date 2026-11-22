/**
 * Transport behavior (headers, retries, timeouts, cancellation, error mapping) exercised through
 * the workflows product, which is how applications reach the shared core transport.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  APIConnectionError,
  APITimeoutError,
  InternalServerError,
  InvalidResponseError,
  RequestAbortedError,
  VERSION,
} from "@traceport/core";
import {
  envelope,
  errorEnvelope,
  stalledResponse,
  testClient,
  type RecordedRequest,
} from "../../../test-utils/helpers.js";

const VERSION_ID = "00000000-0000-4000-8000-000000000001";
const RUN = {
  id: "00000000-0000-4000-8000-000000000002",
  configVersionID: VERSION_ID,
  revision: 1,
  status: "queued",
  mode: "production",
  source: "api_async",
  createdAt: "2026-11-12T10:00:00Z",
};
const RESULT = { data: { final: { ok: true } }, error: "", steps: [] };

/** A fetch step that never answers until its signal aborts, like a hung connection. */
function hang(_request: RecordedRequest, signal: AbortSignal | undefined): Promise<Response> {
  return new Promise((_resolve, reject) => {
    signal?.addEventListener("abort", () => {
      reject(new DOMException("aborted", "AbortError"));
    });
  });
}

afterEach(() => {
  vi.useRealTimers();
});

describe("request headers", () => {
  it("sends credentials, JSON headers and a User-Agent", async () => {
    const { workflows, requests } = testClient([envelope(RESULT)]);
    await workflows.execute({ versionId: VERSION_ID });

    const headers = requests[0]!.headers;
    expect(headers.get("authorization")).toBe("Bearer test-key");
    expect(headers.get("accept")).toBe("application/json");
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("user-agent")).toMatch(new RegExp(`^traceport-typescript/${VERSION}`));
  });

  it("sends default input and a generated idempotency key", async () => {
    const { workflows, requests } = testClient([envelope(RESULT)]);
    await workflows.execute({ versionId: VERSION_ID });

    expect(requests[0]!.body).toEqual({ configVersionID: VERSION_ID, additional: {} });
    expect(requests[0]!.headers.get("idempotency-key")).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("merges default and per-request headers but never replaces Authorization", async () => {
    const { workflows, requests } = testClient([envelope(RUN)], {
      defaultHeaders: { "x-team": "a", Authorization: "Bearer other" },
    });
    await workflows.runs.get(RUN.id, { headers: { traceparent: "00-abc-def-01" } });

    const headers = requests[0]!.headers;
    expect(headers.get("x-team")).toBe("a");
    expect(headers.get("traceparent")).toBe("00-abc-def-01");
    expect(headers.get("authorization")).toBe("Bearer test-key");
  });

  it("omits Content-Type and Idempotency-Key on reads", async () => {
    const { workflows, requests } = testClient([envelope(RUN)]);
    await workflows.runs.get(RUN.id);

    expect(requests[0]!.headers.has("content-type")).toBe(false);
    expect(requests[0]!.headers.has("idempotency-key")).toBe(false);
  });

  it.each(["execute", "start"] as const)(
    "protects explicit idempotency keys from default and per-request headers on %s",
    async (method) => {
      const reply = envelope(method === "execute" ? RESULT : RUN);
      const { workflows, requests } = testClient([reply, reply], {
        defaultHeaders: { "Idempotency-Key": "shared-default" },
      });
      for (const key of ["job-one", "job-two"]) {
        const params = { versionId: VERSION_ID };
        const options = { idempotencyKey: key, headers: { "IDEMPOTENCY-KEY": "" } };
        if (method === "execute") await workflows.execute(params, options);
        else await workflows.runs.start(params, options);
      }
      expect(requests.map((request) => request.headers.get("idempotency-key"))).toEqual([
        "job-one",
        "job-two",
      ]);
    },
  );

  it("protects generated keys and omits stray idempotency headers on reads", async () => {
    const { workflows, requests } = testClient([envelope(RUN), envelope(RUN)], {
      defaultHeaders: { "Idempotency-Key": "" },
    });
    await workflows.runs.start({ versionId: VERSION_ID });
    await workflows.runs.get(RUN.id, { headers: { "idempotency-key": "stray-key" } });
    expect(requests[0]!.headers.get("idempotency-key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(requests[1]!.headers.has("idempotency-key")).toBe(false);
  });
});

describe("per-request option validation", () => {
  it.each([
    { timeout: 0 },
    { timeout: -1 },
    { timeout: Number.NaN },
    { timeout: Infinity },
    { timeout: 2 ** 31 },
    { maxRetries: -1 },
    { maxRetries: 1.5 },
    { maxRetries: Number.NaN },
    { maxRetries: Infinity },
    { maxRetries: Number.MAX_SAFE_INTEGER + 1 },
  ])("rejects invalid settings before sending a request: %j", async (options) => {
    const { workflows, requests } = testClient([]);
    await expect(workflows.runs.get(RUN.id, options)).rejects.toBeInstanceOf(TypeError);
    expect(requests).toHaveLength(0);
  });
});

describe("retries", () => {
  it("retries a transient failure with the same key and body", async () => {
    const { workflows, requests } = testClient(
      [
        {
          ...errorEnvelope(503, "unavailable", "workflow_executor_unavailable"),
          headers: { "Retry-After": "0" },
        },
        envelope(RUN, 202),
      ],
      { maxRetries: 2 },
    );
    const run = await workflows.runs.start({ versionId: VERSION_ID, input: { a: 1 } });

    expect(run.id).toBe(RUN.id);
    expect(requests).toHaveLength(2);
    expect(requests[1]!.headers.get("idempotency-key")).toBe(
      requests[0]!.headers.get("idempotency-key"),
    );
    expect(requests[1]!.body).toEqual(requests[0]!.body);
  });

  it("honors Retry-After before retrying", async () => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient(
      [{ ...errorEnvelope(503, "unavailable"), headers: { "Retry-After": "2" } }, envelope(RUN)],
      { maxRetries: 1 },
    );
    const pending = workflows.runs.get(RUN.id);

    await vi.advanceTimersByTimeAsync(1_900);
    expect(requests).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(200);
    await expect(pending).resolves.toMatchObject({ id: RUN.id });
    expect(requests).toHaveLength(2);
  });

  it("stops after maxRetries and throws the last error", async () => {
    vi.useFakeTimers();
    const failure = errorEnvelope(500, "something went wrong", "traceport-0000");
    const { workflows, requests } = testClient([failure, failure, failure], { maxRetries: 2 });
    const pending = workflows.runs.get(RUN.id).catch((e: unknown) => e);

    await vi.runAllTimersAsync();
    const error = await pending;
    expect(error).toBeInstanceOf(InternalServerError);
    expect(requests).toHaveLength(3);
  });

  it("does not retry client errors", async () => {
    const { workflows, requests } = testClient([errorEnvelope(404, "workflow run not found")], {
      maxRetries: 2,
    });
    await expect(workflows.runs.get(RUN.id)).rejects.toMatchObject({ status: 404 });
    expect(requests).toHaveLength(1);
  });

  it("retries connection failures", async () => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient(
      [{ throws: new TypeError("fetch failed") }, envelope(RUN)],
      { maxRetries: 1 },
    );
    const pending = workflows.runs.get(RUN.id);
    await vi.runAllTimersAsync();

    await expect(pending).resolves.toMatchObject({ id: RUN.id });
    expect(requests).toHaveLength(2);
  });

  it("throws APIConnectionError when connection failures persist", async () => {
    const { workflows } = testClient([{ throws: new TypeError("fetch failed") }]);
    const error = await workflows.runs.get(RUN.id).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(APIConnectionError);
    expect((error as Error).cause).toBeInstanceOf(TypeError);
  });

  it("allows per-request maxRetries", async () => {
    const { workflows, requests } = testClient([errorEnvelope(503, "x"), envelope(RUN)], {
      maxRetries: 0,
    });
    await workflows.runs.get(RUN.id, { maxRetries: 1 }).catch(() => undefined);
    expect(requests).toHaveLength(2);
  });
});

describe("timeouts and cancellation", () => {
  it.each([200, 503])("times out a stalled HTTP %i response body", async (status) => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient([
      (_request, signal) => Promise.resolve(stalledResponse(signal, status)),
    ]);
    const pending = workflows.runs.get(RUN.id, { timeout: 100 }).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(100);
    expect(await pending).toBeInstanceOf(APITimeoutError);
    expect(requests).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("retries a stalled read body with a fresh attempt", async () => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient(
      [(_request, signal) => Promise.resolve(stalledResponse(signal)), envelope(RUN)],
      { timeout: 100, maxRetries: 1 },
    );
    const pending = workflows.runs.get(RUN.id);
    await vi.runAllTimersAsync();
    await expect(pending).resolves.toMatchObject({ id: RUN.id });
    expect(requests).toHaveLength(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not retry an execute whose response body timed out", async () => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient(
      [(_request, signal) => Promise.resolve(stalledResponse(signal)), envelope(RESULT)],
      { maxRetries: 2 },
    );
    const pending = workflows
      .execute({ versionId: VERSION_ID }, { timeout: 100 })
      .catch((error: unknown) => error);
    await vi.runAllTimersAsync();
    expect(await pending).toBeInstanceOf(APITimeoutError);
    expect(requests).toHaveLength(1);
  });

  it("honors caller cancellation after headers arrive without retrying", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const reason = new Error("caller cancelled");
    const { workflows, requests } = testClient(
      [(_request, signal) => Promise.resolve(stalledResponse(signal)), envelope(RUN)],
      { maxRetries: 2 },
    );
    const pending = workflows.runs
      .get(RUN.id, { signal: controller.signal })
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(0);
    controller.abort(reason);
    expect(await pending).toMatchObject({ name: "RequestAbortedError", cause: reason });
    expect(requests).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("enforces timeouts when custom fetch ignores the abort signal", async () => {
    vi.useFakeTimers();
    const { workflows } = testClient([() => Promise.resolve(stalledResponse())]);
    const pending = workflows.runs.get(RUN.id, { timeout: 100 }).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(100);
    expect(await pending).toBeInstanceOf(APITimeoutError);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("times out a hung request", async () => {
    vi.useFakeTimers();
    const { workflows } = testClient([hang], { timeout: 1_000 });
    const pending = workflows.runs.get(RUN.id).catch((e: unknown) => e);

    await vi.advanceTimersByTimeAsync(1_000);
    expect(await pending).toBeInstanceOf(APITimeoutError);
  });

  it("retries a timed-out read", async () => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient([hang, envelope(RUN)], {
      timeout: 1_000,
      maxRetries: 1,
    });
    const pending = workflows.runs.get(RUN.id);

    await vi.runAllTimersAsync();
    await expect(pending).resolves.toMatchObject({ id: RUN.id });
    expect(requests).toHaveLength(2);
  });

  it("does not retry a timed-out execute, because the workflow keeps running", async () => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient([hang, envelope(RESULT)], { maxRetries: 2 });
    const pending = workflows
      .execute({ versionId: VERSION_ID }, { timeout: 1_000 })
      .catch((e: unknown) => e);

    await vi.advanceTimersByTimeAsync(5_000);
    expect(await pending).toBeInstanceOf(APITimeoutError);
    expect(requests).toHaveLength(1);
  });

  it("gives execute at least 6 minutes by default", async () => {
    vi.useFakeTimers();
    const { workflows } = testClient([hang], { timeout: 1_000 });
    let settled = false;
    const pending = workflows
      .execute({ versionId: VERSION_ID })
      .catch((e: unknown) => e)
      .finally(() => (settled = true));

    await vi.advanceTimersByTimeAsync(5 * 60_000);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(await pending).toBeInstanceOf(APITimeoutError);
  });

  it("throws RequestAbortedError when the caller aborts, without retrying", async () => {
    const controller = new AbortController();
    const { workflows, requests } = testClient([hang, envelope(RUN)], { maxRetries: 2 });
    const pending = workflows.runs
      .get(RUN.id, { signal: controller.signal })
      .catch((e: unknown) => e);

    controller.abort();
    expect(await pending).toBeInstanceOf(RequestAbortedError);
    expect(requests).toHaveLength(1);
  });

  it("rejects immediately when the signal is already aborted", async () => {
    const { workflows, requests } = testClient([envelope(RUN)]);
    await expect(
      workflows.runs.get(RUN.id, { signal: AbortSignal.abort() }),
    ).rejects.toBeInstanceOf(RequestAbortedError);
    expect(requests).toHaveLength(0);
  });
});

describe("response parsing", () => {
  it.each([200, 503])("retries connection failures reading an HTTP %i body", async (status) => {
    vi.useFakeTimers();
    const { workflows, requests } = testClient(
      [
        () =>
          Promise.resolve(
            new Response(
              new ReadableStream({
                start(controller) {
                  controller.error(new TypeError("socket closed"));
                },
              }),
              { status },
            ),
          ),
        envelope(RUN),
      ],
      { maxRetries: 1 },
    );
    const pending = workflows.runs.get(RUN.id);
    await vi.runAllTimersAsync();
    await expect(pending).resolves.toMatchObject({ id: RUN.id });
    expect(requests).toHaveLength(2);
  });

  it("wraps an unrecoverable body connection failure", async () => {
    const cause = new TypeError("socket closed");
    const { workflows } = testClient([
      () =>
        Promise.resolve(
          new Response(
            new ReadableStream({
              start(controller) {
                controller.error(cause);
              },
            }),
          ),
        ),
    ]);
    await expect(workflows.runs.get(RUN.id)).rejects.toMatchObject({
      name: "APIConnectionError",
      cause,
    });
  });

  it("does not retry or relabel a malformed success envelope", async () => {
    const { workflows, requests } = testClient([{ status: 200, body: "not an envelope" }], {
      maxRetries: 2,
    });
    await expect(workflows.runs.get(RUN.id)).rejects.toBeInstanceOf(InvalidResponseError);
    expect(requests).toHaveLength(1);
  });

  it("maps a non-JSON error page to a typed error", async () => {
    const { workflows } = testClient([{ status: 502, body: "<html>Bad gateway</html>" }]);
    const error = await workflows.runs.get(RUN.id).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(InternalServerError);
    expect((error as InternalServerError).message).toBe("request failed with HTTP 502");
    expect((error as InternalServerError).body).toBe("<html>Bad gateway</html>");
  });

  it("rejects a success response without an envelope", async () => {
    const { workflows } = testClient([{ status: 200, body: "ok" }]);
    await expect(workflows.runs.get(RUN.id)).rejects.toBeInstanceOf(InvalidResponseError);
  });

  it("rejects a success envelope that reports an error", async () => {
    const { workflows } = testClient([
      { status: 200, body: { data: null, error: "boom", status: 200 } },
    ]);
    await expect(workflows.runs.get(RUN.id)).rejects.toBeInstanceOf(InvalidResponseError);
  });

  it("exposes the request ID header on errors", async () => {
    const { workflows } = testClient([
      { ...errorEnvelope(404, "nope"), headers: { "x-request-id": "req_1" } },
    ]);
    await expect(workflows.runs.get(RUN.id)).rejects.toMatchObject({ requestId: "req_1" });
  });
});
