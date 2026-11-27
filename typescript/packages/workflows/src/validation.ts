/**
 * Client-side argument checks. These catch programming mistakes before a request is sent and
 * throw `TypeError`, like the platform does for invalid arguments.
 */

import { isRecord, randomIdempotencyKey } from "@traceport/core/internal";
import type { WorkflowStartParams } from "./types.js";

/** The server's limit: at most 200 bytes, without whitespace or control characters. */
const MAX_IDEMPOTENCY_KEY_BYTES = 200;
// eslint-disable-next-line no-control-regex -- matching control characters is the point.
const INVALID_KEY_CHARACTERS = /[\s\u0000-\u001f\u007f-\u009f]/u;

/** Returns `key` after validating it, or a new random key when `key` is undefined. */
export function resolveIdempotencyKey(key: string | undefined): string {
  if (key === undefined) return randomIdempotencyKey();
  if (key === "" || new TextEncoder().encode(key).length > MAX_IDEMPOTENCY_KEY_BYTES) {
    throw new TypeError(`idempotencyKey must be 1-${MAX_IDEMPOTENCY_KEY_BYTES} bytes`);
  }
  if (INVALID_KEY_CHARACTERS.test(key)) {
    throw new TypeError("idempotencyKey must not contain whitespace or control characters");
  }
  return key;
}

/** Validates a resource ID argument. */
export function requireId(value: string, name: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new TypeError(`${name} must be a non-empty string`);
  }
  return value;
}

/** Maps SDK parameters to the request body the API expects. */
export function startBody(params: WorkflowStartParams): {
  configVersionID?: string;
  deployment?: string;
  additional: Record<string, unknown>;
} {
  // `params` may come from untyped JavaScript callers.
  if (!isRecord(params)) throw new TypeError("params must be an object");
  const input = params.input ?? {};
  if (!isRecord(input)) throw new TypeError("input must be a plain object");
  const hasDeployment = params.deployment !== undefined;
  const hasVersion = params.versionId !== undefined;
  if (hasDeployment === hasVersion) {
    throw new TypeError("pass exactly one of deployment or versionId");
  }
  return hasDeployment
    ? { deployment: requireId(params.deployment, "deployment"), additional: input }
    : { configVersionID: requireId(params.versionId, "versionId"), additional: input };
}
