/** Shared validation for client, per-request and polling settings. */

/** Largest delay supported by the runtimes' signed 32-bit timers. */
const MAX_TIMER_MS = 2 ** 31 - 1;

export function validateTimeout(value: number, name: string): void {
  if (!Number.isFinite(value) || value <= 0 || value > MAX_TIMER_MS) {
    throw new TypeError(`${name} must be a positive number no greater than ${MAX_TIMER_MS}`);
  }
}

export function validateMaxRetries(value: number): void {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new TypeError("maxRetries must be a non-negative safe integer");
  }
}
