/**
 * Core client: construction, derived clients, the product-facing transport and package metadata.
 * Requests go through `transportOf`, the same entry point product packages use.
 */

import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_BASE_URL, Traceport, TraceportError, VERSION } from "../src/index.js";
import { transportOf } from "../src/internal.js";
import { envelope, mockFetch } from "../../../test-utils/helpers.js";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

/** Sends a GET through the client's shared transport, as a product package would. */
function get(client: Traceport, path = "/ping"): Promise<unknown> {
  return transportOf(client).request({ method: "GET", path, retryOnTimeout: true });
}

describe("Traceport client", () => {
  it("requires an API key", () => {
    vi.stubEnv("TRACEPORT_API_KEY", "");
    expect(() => new Traceport()).toThrow(TraceportError);
  });

  it("reads the API key and base URL from the environment", async () => {
    vi.stubEnv("TRACEPORT_API_KEY", "env-key");
    vi.stubEnv("TRACEPORT_BASE_URL", "https://env.test/v1/");
    const { fetch, requests } = mockFetch([envelope({ ok: true })]);
    const client = new Traceport({ fetch });

    expect(client.baseURL).toBe("https://env.test/v1");
    await get(client, "/workflow/runs");
    expect(requests[0]!.url.toString()).toBe("https://env.test/v1/workflow/runs");
    expect(requests[0]!.headers.get("authorization")).toBe("Bearer env-key");
  });

  it("defaults to the public API", () => {
    vi.stubEnv("TRACEPORT_BASE_URL", "");
    expect(new Traceport({ apiKey: "k" }).baseURL).toBe(DEFAULT_BASE_URL);
  });

  it("refuses to run in a browser unless explicitly allowed", () => {
    vi.stubGlobal("window", {});
    vi.stubGlobal("document", {});
    expect(() => new Traceport({ apiKey: "k" })).toThrow(/browser/);
    expect(() => new Traceport({ apiKey: "k", dangerouslyAllowBrowser: true })).not.toThrow();
  });

  it.each([{ timeout: 0 }, { timeout: Number.NaN }, { maxRetries: -1 }, { maxRetries: 1.5 }])(
    "rejects invalid option %j",
    (options) => {
      expect(() => new Traceport({ apiKey: "k", ...options })).toThrow(TypeError);
    },
  );
});

describe("withOptions", () => {
  it("keeps credentials, base URL and fetch, and merges default headers", async () => {
    const { fetch, requests } = mockFetch([envelope({}), envelope({})]);
    const client = new Traceport({
      apiKey: "k",
      baseURL: "https://api.test/v1",
      fetch,
      defaultHeaders: { "x-team": "a", "x-keep": "1" },
    });
    const derived = client.withOptions({ defaultHeaders: { "x-team": "b" } });

    expect(derived).not.toBe(client);
    expect(derived).toBeInstanceOf(Traceport);
    expect(derived.baseURL).toBe(client.baseURL);
    await get(client);
    await get(derived);
    expect(requests).toHaveLength(2);
    expect(requests[1]!.url.href).toBe("https://api.test/v1/ping");
    expect(requests[1]!.headers.get("authorization")).toBe("Bearer k");
    expect(requests[1]!.headers.get("x-team")).toBe("b");
    expect(requests[1]!.headers.get("x-keep")).toBe("1");
    expect(requests[0]!.headers.get("x-team")).toBe("a");
  });

  it("applies new retry settings without changing the original client", async () => {
    const failing = { status: 503, body: { data: null, error: "x", status: 503, errorCode: "" } };
    const { fetch, requests } = mockFetch([failing, failing, envelope({})]);
    const client = new Traceport({
      apiKey: "k",
      baseURL: "https://api.test/v1",
      fetch,
      maxRetries: 0,
    });

    await expect(get(client)).rejects.toMatchObject({ status: 503 });
    expect(requests).toHaveLength(1);
    await get(client.withOptions({ maxRetries: 1 }).withOptions({ timeout: 5_000 })).catch(
      () => undefined,
    );
    // One attempt plus one retry for the derived client; the original stays at zero retries.
    expect(requests).toHaveLength(3);
  });

  it("validates overrides", () => {
    const client = new Traceport({ apiKey: "k" });
    expect(() => client.withOptions({ timeout: -1 })).toThrow(TypeError);
  });

  it("returns the caller's subclass", () => {
    class Extended extends Traceport {
      readonly extra = "yes";
    }
    expect(new Extended({ apiKey: "k" }).withOptions({ timeout: 1_000 }).extra).toBe("yes");
  });
});

describe("transportOf", () => {
  it("rejects objects that are not Traceport clients", () => {
    expect(() => transportOf({ baseURL: "x" } as unknown as Traceport)).toThrow(
      /expected a Traceport client/,
    );
  });

  it("gives every product the same transport for one client", () => {
    const client = new Traceport({ apiKey: "k" });
    expect(transportOf(client)).toBe(transportOf(client));
    expect(transportOf(client.withOptions({}))).not.toBe(transportOf(client));
  });
});

describe("package metadata", () => {
  it("VERSION matches package.json", () => {
    const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")) as {
      version: string;
    };
    expect(VERSION).toBe(pkg.version);
  });
});
