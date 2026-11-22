/**
 * Small runtime helpers that work the same in Node.js, Bun, Deno and edge runtimes.
 */

import { RequestAbortedError } from "./errors.js";

/** Reads an environment variable when the runtime exposes `process.env`, without throwing. */
export function readEnv(name: string): string | undefined {
  // `process` is not defined in browsers and some edge runtimes, so look it up defensively.
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process
    ?.env;
  const value = env?.[name]?.trim();
  return value === "" ? undefined : value;
}

/** True when running in a web page, where an API key would be visible to every visitor. */
export function isBrowser(): boolean {
  return (
    typeof (globalThis as { window?: unknown }).window !== "undefined" &&
    typeof (globalThis as { document?: unknown }).document !== "undefined"
  );
}

/** Generates a random idempotency key (a UUID v4). */
export function randomIdempotencyKey(): string {
  return globalThis.crypto.randomUUID();
}

/** Enforces cancellation even when a custom fetch implementation ignores its signal. */
export async function withSignal<T>(signal: AbortSignal, action: () => Promise<T>): Promise<T> {
  if (signal.aborted) {
    throw new RequestAbortedError("request was aborted", { cause: signal.reason });
  }
  let onAbort: (() => void) | undefined;
  const aborted = new Promise<never>((_resolve, reject) => {
    onAbort = (): void => {
      reject(new RequestAbortedError("request was aborted", { cause: signal.reason }));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
  try {
    return await Promise.race([action(), aborted]);
  } finally {
    if (onAbort !== undefined) signal.removeEventListener("abort", onAbort);
  }
}

/** Resolves after `ms` milliseconds, or rejects with {@link RequestAbortedError} if `signal` aborts first. */
export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new RequestAbortedError("request was aborted", { cause: signal.reason }));
      return;
    }
    const onAbort = (): void => {
      clearTimeout(timer);
      reject(new RequestAbortedError("request was aborted", { cause: signal?.reason }));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/** True for plain JSON objects (not arrays or null). */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
