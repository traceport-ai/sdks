/**
 * Internal building blocks for Traceport product packages (`@traceport/workflows`, …).
 *
 * Not part of the public API and not covered by semantic versioning: application code should not
 * import `@traceport/core/internal`. Product packages pin a compatible `@traceport/core` range
 * through their peer dependency.
 *
 * @packageDocumentation
 * @internal
 */

export { transportOf } from "./client.js";
export { Transport, type APIRequest, type APIResponse, type TransportConfig } from "./transport.js";
export { isRecord, randomIdempotencyKey, sleep, withSignal } from "./runtime.js";
export { validateMaxRetries, validateTimeout } from "./validation.js";
