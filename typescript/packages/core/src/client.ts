/**
 * The Traceport API client shared by every product package.
 *
 * The client owns configuration and HTTP only. Products (`@traceport/workflows`, later
 * `@traceport/documents`) take a client in their constructor and send requests through it, so one
 * client, configured once, serves every product.
 */

import { TraceportError } from "./errors.js";
import { isBrowser, readEnv } from "./runtime.js";
import { Transport, type Fetch } from "./transport.js";
import { validateMaxRetries, validateTimeout } from "./validation.js";

/** Default API base URL. Paths such as `/workflow/runs` are appended to it. */
export const DEFAULT_BASE_URL = "https://api.traceport.ai/v1";
const DEFAULT_TIMEOUT_MS = 60_000;
const DEFAULT_MAX_RETRIES = 2;

/** Settings for {@link Traceport}. Every field is optional. */
export interface ClientOptions {
  /** Traceport API key. Defaults to the `TRACEPORT_API_KEY` environment variable. */
  apiKey?: string;
  /**
   * API base URL including the `/v1` prefix. Defaults to `TRACEPORT_BASE_URL`, then
   * `https://api.traceport.ai/v1`.
   */
  baseURL?: string;
  /**
   * Request timeout in milliseconds. Default 60 seconds. Some product operations wait longer by
   * default (for example, workflow `execute` waits at least 6 minutes).
   */
  timeout?: number;
  /** Automatic retries for transient failures. Default 2. Set 0 to disable. */
  maxRetries?: number;
  /** Custom `fetch` implementation, for example to add a proxy or for tests. */
  fetch?: Fetch;
  /** Headers sent with every request. Cannot override `Authorization` or `Idempotency-Key`. */
  defaultHeaders?: Record<string, string>;
  /**
   * Allow use in a web browser. Off by default: an API key in a web page is visible to every
   * visitor. Call Traceport from your server, or from a backend route your page calls.
   */
  dangerouslyAllowBrowser?: boolean;
}

/**
 * Settings a derived client may change. Credentials, base URL and `fetch` stay the same, so a
 * derived client always talks to the same API as the same organization.
 */
export type ClientOverrides = Pick<ClientOptions, "timeout" | "maxRetries" | "defaultHeaders">;

/** Fully resolved settings, kept so {@link Traceport.withOptions} can derive a client. */
interface ResolvedOptions {
  apiKey: string;
  baseURL: string;
  timeout: number;
  maxRetries: number;
  fetch: Fetch;
  defaultHeaders: Record<string, string>;
  dangerouslyAllowBrowser: boolean;
}

/**
 * Transport for each client. Product packages read it through `transportOf` in
 * `@traceport/core/internal`; it is deliberately not a public property.
 */
const transports = new WeakMap<Traceport, Transport>();
const resolvedOptions = new WeakMap<Traceport, ResolvedOptions>();

/**
 * Client for the Traceport API. Create one and pass it to each product you use.
 *
 * @example
 * import { Traceport } from "@traceport/core";
 * import { Workflows } from "@traceport/workflows";
 *
 * const client = new Traceport(); // reads TRACEPORT_API_KEY
 * const workflows = new Workflows(client);
 */
export class Traceport {
  /** The resolved base URL, without a trailing slash. */
  readonly baseURL: string;

  constructor(options: ClientOptions = {}) {
    const apiKey = options.apiKey ?? readEnv("TRACEPORT_API_KEY");
    if (apiKey === undefined || apiKey.trim() === "") {
      throw new TraceportError(
        "missing API key: pass `apiKey` or set the TRACEPORT_API_KEY environment variable",
      );
    }
    const dangerouslyAllowBrowser = options.dangerouslyAllowBrowser === true;
    if (isBrowser() && !dangerouslyAllowBrowser) {
      throw new TraceportError(
        "the Traceport SDK is meant for servers; using it in a browser exposes your API key. " +
          "Call Traceport from your backend, or set `dangerouslyAllowBrowser: true` if you understand the risk",
      );
    }

    const timeout = options.timeout ?? DEFAULT_TIMEOUT_MS;
    const maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
    validateTimeout(timeout, "timeout");
    validateMaxRetries(maxRetries);

    const fetchImpl = options.fetch ?? globalThis.fetch;
    if (typeof fetchImpl !== "function") {
      throw new TraceportError("no global fetch is available; pass a `fetch` implementation");
    }

    this.baseURL = (options.baseURL ?? readEnv("TRACEPORT_BASE_URL") ?? DEFAULT_BASE_URL).replace(
      /\/+$/,
      "",
    );
    const resolved: ResolvedOptions = {
      apiKey,
      baseURL: this.baseURL,
      timeout,
      maxRetries,
      fetch: fetchImpl,
      defaultHeaders: { ...options.defaultHeaders },
      dangerouslyAllowBrowser,
    };
    resolvedOptions.set(this, resolved);
    transports.set(
      this,
      new Transport({
        apiKey,
        baseURL: this.baseURL,
        timeout,
        maxRetries,
        // Bind so implementations that rely on `this === globalThis` keep working.
        fetch: fetchImpl.bind(globalThis),
        defaultHeaders: resolved.defaultHeaders,
      }),
    );
  }

  /**
   * Returns a new client with the same credentials, base URL and `fetch`, but different timeouts,
   * retries or default headers. Use it to give one product different settings without configuring
   * a second client. `defaultHeaders` are merged over this client's headers.
   *
   * The result has this client's class, so a subclass of `Traceport` stays that subclass.
   *
   * @example
   * const patient = client.withOptions({ timeout: 300_000, maxRetries: 5 });
   * const workflows = new Workflows(patient);
   */
  withOptions(overrides: ClientOverrides): this {
    const current = resolvedOptions.get(this);
    if (current === undefined) throw new TypeError("withOptions called on an uninitialized client");
    const options: ClientOptions = {
      apiKey: current.apiKey,
      baseURL: current.baseURL,
      timeout: overrides.timeout ?? current.timeout,
      maxRetries: overrides.maxRetries ?? current.maxRetries,
      fetch: current.fetch,
      defaultHeaders: { ...current.defaultHeaders, ...overrides.defaultHeaders },
      dangerouslyAllowBrowser: current.dangerouslyAllowBrowser,
    };
    const Derived = this.constructor as new (options: ClientOptions) => this;
    return new Derived(options);
  }
}

/**
 * Returns the transport of a client. Internal: exported to product packages through
 * `@traceport/core/internal`, not part of the public API.
 *
 * @throws {TypeError} `client` was not created by this copy of `@traceport/core`. This also happens
 *   when an application ends up with two copies of `@traceport/core`; install a single version.
 */
export function transportOf(client: Traceport): Transport {
  const transport = transports.get(client);
  if (transport === undefined) {
    throw new TypeError(
      "expected a Traceport client from @traceport/core; if you passed one, make sure only one " +
        "copy of @traceport/core is installed (npm ls @traceport/core)",
    );
  }
  return transport;
}
