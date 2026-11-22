/**
 * Test helpers: a scripted `fetch` and loaders for the shared fixtures and contract.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { Traceport, type ClientOptions } from "@traceport/core";
import { Workflows } from "@traceport/workflows";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));

/** A request as seen by the mock fetch. */
export interface RecordedRequest {
  method: string;
  url: URL;
  headers: Headers;
  body: unknown;
}

/** A scripted response: status, optional headers and a JSON (or raw string) body. */
export interface MockResponse {
  status: number;
  headers?: Record<string, string>;
  body?: unknown;
}

/** One scripted reply: a response, an error to throw, or a function computing either. */
export type MockStep =
  | MockResponse
  | { throws: unknown }
  | ((request: RecordedRequest, signal: AbortSignal | undefined) => Promise<Response>);

/** A `fetch` that replays `steps` in order and records every request. */
export function mockFetch(steps: MockStep[]): {
  fetch: typeof globalThis.fetch;
  requests: RecordedRequest[];
} {
  const requests: RecordedRequest[] = [];
  const queue = [...steps];
  const fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const text = typeof init?.body === "string" ? init.body : undefined;
    const request: RecordedRequest = {
      method: init?.method ?? "GET",
      url: new URL(input instanceof Request ? input.url : input.toString()),
      headers: new Headers(init?.headers),
      body: text === undefined ? undefined : JSON.parse(text),
    };
    requests.push(request);
    const step = queue.shift();
    if (step === undefined) {
      throw new Error(`unexpected request ${request.method} ${request.url.href}`);
    }
    if (typeof step === "function") return step(request, init?.signal ?? undefined);
    if ("throws" in step) throw step.throws;
    return jsonResponse(step);
  }) as typeof globalThis.fetch;
  return { fetch, requests };
}

/** Builds a `Response` from a scripted step. */
export function jsonResponse(step: MockResponse): Response {
  const body =
    step.body === undefined
      ? null
      : typeof step.body === "string"
        ? step.body
        : JSON.stringify(step.body);
  return new Response(body, {
    status: step.status,
    headers: { "content-type": "application/json", ...step.headers },
  });
}

/** Headers arrive immediately, but the response body stalls until the fetch signal aborts. */
export function stalledResponse(signal?: AbortSignal, status = 200): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        signal?.addEventListener(
          "abort",
          () => {
            controller.error(signal.reason);
          },
          { once: true },
        );
      },
    }),
    { status },
  );
}

/**
 * A core client wired to a scripted fetch (retries off unless overridden), and the workflows
 * product built on it.
 */
export function testClient(
  steps: MockStep[],
  options: ClientOptions = {},
): { client: Traceport; workflows: Workflows; requests: RecordedRequest[] } {
  const { fetch, requests } = mockFetch(steps);
  const client = new Traceport({
    apiKey: "test-key",
    baseURL: "https://api.test/v1",
    maxRetries: 0,
    fetch,
    ...options,
  });
  return { client, workflows: new Workflows(client), requests };
}

/** A successful envelope around `data`. */
export function envelope(data: unknown, status = 200): MockResponse {
  return { status, body: { data, error: "", status, errorCode: "" } };
}

/** An error envelope. */
export function errorEnvelope(status: number, error: string, errorCode = ""): MockResponse {
  return { status, body: { data: null, error, status, errorCode } };
}

/** Shape of a shared fixture file (see fixtures/README.md). */
export interface Fixture {
  file: string;
  name: string;
  operation: "executeWorkflow" | "startWorkflowRun" | "getWorkflowRun" | "listWorkflowRuns";
  request: { method: string; path: string; headers?: Record<string, string>; body?: unknown };
  response: { status: number; headers?: Record<string, string>; body: unknown };
  expect: {
    kind: "resource" | "outcome" | "error";
    resource?: Record<string, unknown>;
    outcome?: { status: string; output: unknown; error?: string; stepCount?: number };
    error?: {
      class: string;
      status: number;
      errorCode: string;
      retryable: boolean;
      existingRunId?: string;
    };
  };
}

/** Loads every shared fixture from the repository's `fixtures/` folder. */
export function loadFixtures(): Fixture[] {
  const root = join(REPO_ROOT, "fixtures");
  const files = (readdirSync(root, { recursive: true }) as string[])
    .filter((file) => file.endsWith(".json"))
    .sort();
  return files.map((file) => ({
    file: relative(REPO_ROOT, join(root, file)),
    ...(JSON.parse(readFileSync(join(root, file), "utf8")) as Omit<Fixture, "file">),
  }));
}

/** The parts of the OpenAPI snapshot the contract test reads. */
export interface Contract {
  components: { schemas: Record<string, { properties?: Record<string, { enum?: string[] }> }> };
}

/** Loads the public OpenAPI snapshot. */
export function loadContract(): Contract {
  return JSON.parse(readFileSync(join(REPO_ROOT, "contract", "openapi.json"), "utf8")) as Contract;
}
