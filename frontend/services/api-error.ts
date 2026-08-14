/**
 * Why a request failed, in terms the UI can act on.
 *
 * The kind drives two decisions the UI cannot make from a bare status code:
 * what to tell the user, and whether retrying could possibly help. A 503 from
 * an unbuilt index and a 429 from rate limiting both "failed", but one is a
 * setup problem the user must fix and the other resolves by waiting.
 */
export type ApiErrorKind =
  | "network" // the request never reached the server
  | "timeout" // no response within the deadline
  | "cancelled" // the caller aborted — not a failure, and never shown as one
  | "bad_request" // 400/422 — the request itself is wrong
  | "not_found" // 404
  | "rate_limited" // 429
  | "unavailable" // 503 — index missing or GROQ_API_KEY unset
  | "server" // 5xx
  | "parse"; // response body was not the shape we expected

/** Kinds where retrying the identical request could succeed. */
const RETRYABLE: ReadonlySet<ApiErrorKind> = new Set<ApiErrorKind>([
  "network",
  "timeout",
  "rate_limited",
  "server",
]);

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  /** FastAPI's `detail` field when present — the actionable part of the message. */
  readonly detail?: string;

  constructor(
    kind: ApiErrorKind,
    message: string,
    options: { status?: number; detail?: string; cause?: unknown } = {},
  ) {
    super(message, { cause: options.cause });
    this.name = "ApiError";
    this.kind = kind;
    this.status = options.status;
    this.detail = options.detail;
  }

  /**
   * Whether retrying makes sense.
   *
   * 503 is deliberately absent: an unbuilt index or a missing API key does not
   * fix itself, so retrying burns time and hides the real cause. This mirrors
   * GroqGenerator._call_with_retry on the backend, which retries rate limits
   * and connection errors but fails fast on auth and bad requests.
   */
  get retryable(): boolean {
    return RETRYABLE.has(this.kind);
  }

  /** Message suitable for display, preferring the server's own explanation. */
  get userMessage(): string {
    return this.detail ?? this.message;
  }
}

export function kindForStatus(status: number): ApiErrorKind {
  if (status === 400 || status === 422) return "bad_request";
  if (status === 404) return "not_found";
  if (status === 429) return "rate_limited";
  if (status === 503) return "unavailable";
  // 504 is a gateway timeout — the deadline was exceeded upstream, which is
  // the same situation for the user as a client-side timeout.
  if (status === 504) return "timeout";
  if (status >= 500) return "server";
  return "server";
}
