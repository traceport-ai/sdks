/**
 * Core of the Traceport TypeScript SDK: the shared client, request options and error classes.
 *
 * Install the product packages you use (for example `@traceport/workflows`) and pass each of
 * them this client.
 *
 * @packageDocumentation
 */

export { Traceport, DEFAULT_BASE_URL, type ClientOptions, type ClientOverrides } from "./client.js";
export type { Fetch, MutationRequestOptions, RequestOptions } from "./transport.js";
export {
  APIConnectionError,
  APIError,
  APITimeoutError,
  AuthenticationError,
  BadRequestError,
  ConflictError,
  InternalServerError,
  InvalidResponseError,
  NotFoundError,
  PaymentRequiredError,
  PermissionDeniedError,
  RateLimitError,
  RequestAbortedError,
  TraceportError,
  type APIErrorInit,
} from "./errors.js";
export { VERSION } from "./version.js";
