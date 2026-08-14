import type {
  HealthResponse,
  MetricsResponse,
  QueryResponse,
  StreamEvent,
} from "@/types/api";

import { ApiError, kindForStatus } from "./api-error";

/**
 * The only module in the app that talks to the network (ADR 008, enforced by
 * an ESLint rule that bans `fetch` everywhere else).
 *
 * The browser calls FastAPI directly rather than through a Next.js proxy, so
 * the latency this platform reports is the latency the API actually delivered.
 */

const DEFAULT_TIMEOUT_MS = 30_000;

export function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
    /\/+$/,
    "",
  );
}

/** Pull FastAPI's `detail` out of an error body without assuming it is there. */
async function readDetail(response: Response): Promise<string | undefined> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const { detail } = body as { detail: unknown };
      if (typeof detail === "string") return detail;
      // 422 returns a list of validation objects; summarise rather than
      // rendering "[object Object]" at the user.
      if (Array.isArray(detail)) return `${detail.length} validation error(s)`;
    }
  } catch {
    // Body was empty or not JSON — the status alone has to carry the meaning.
  }
  return undefined;
}

/**
 * Classify a rejected fetch by inspecting the signal rather than the exception.
 *
 * Node and browsers disagree on what they throw when a request is aborted —
 * TimeoutError, AbortError, or a TypeError wrapping either — so sniffing the
 * error is unreliable. `signal.aborted` and `signal.reason` are specified.
 */
function abortAwareError(
  signal: AbortSignal,
  path: string,
  timeoutMs: number,
  cause: unknown,
): ApiError {
  if (signal.aborted) {
    const reason = signal.reason as { name?: string } | undefined;
    if (reason?.name === "TimeoutError") {
      return new ApiError(
        "timeout",
        `Request to ${path} timed out after ${timeoutMs} ms`,
        { cause },
      );
    }
    // The caller aborted deliberately — a navigation or a superseded query.
    // Surfacing this as a failure would show an error for something the user
    // asked for.
    return new ApiError("cancelled", `Request to ${path} was cancelled`, { cause });
  }
  return new ApiError("network", `Could not reach the API at ${apiBaseUrl()}`, {
    cause,
  });
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const url = `${apiBaseUrl()}${path}`;

  // Every request carries a deadline. Without one a hung connection leaves a
  // spinner on screen indefinitely, which reads as "broken" with no clue.
  const signal = init.signal ?? AbortSignal.timeout(timeoutMs);

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      signal,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch (cause) {
    // Timeouts, cancellations and refused connections all reject here, and the
    // exception shape differs between runtimes. The signal is authoritative:
    // it records both whether we aborted and why.
    throw abortAwareError(signal, path, timeoutMs, cause);
  }

  if (!response.ok) {
    throw new ApiError(
      kindForStatus(response.status),
      `${init.method ?? "GET"} ${path} failed with ${response.status}`,
      { status: response.status, detail: await readDetail(response) },
    );
  }

  try {
    return (await response.json()) as T;
  } catch (cause) {
    throw new ApiError("parse", `Response from ${path} was not valid JSON`, {
      status: response.status,
      cause,
    });
  }
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  // Short deadline: health is a liveness probe, and a slow one is a failed one.
  return request<HealthResponse>("/health", { signal }, 5_000);
}

export function getMetrics(signal?: AbortSignal): Promise<MetricsResponse> {
  return request<MetricsResponse>("/metrics", { signal }, 5_000);
}

export function postQuery(
  question: string,
  topK?: number,
  signal?: AbortSignal,
): Promise<QueryResponse> {
  return request<QueryResponse>("/query", {
    method: "POST",
    body: JSON.stringify(topK === undefined ? { question } : { question, top_k: topK }),
    signal,
  });
}

/**
 * Stream answer tokens from POST /stream as Server-Sent Events.
 *
 * Yields parsed events so callers never touch the wire format. Undecodable
 * lines are skipped rather than thrown: one malformed token must not discard
 * an answer that is otherwise arriving correctly.
 */
export async function* streamQuery(
  question: string,
  topK?: number,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        topK === undefined ? { question } : { question, top_k: topK },
      ),
      signal,
    });
  } catch (cause) {
    throw abortAwareError(
      signal ?? new AbortController().signal,
      "/stream",
      DEFAULT_TIMEOUT_MS,
      cause,
    );
  }

  if (!response.ok) {
    throw new ApiError(
      kindForStatus(response.status),
      `POST /stream failed with ${response.status}`,
      { status: response.status, detail: await readDetail(response) },
    );
  }
  if (!response.body) {
    throw new ApiError("parse", "Streaming response had no body");
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += value;
      // SSE frames are separated by a blank line. A chunk boundary can split a
      // frame, so only complete frames are consumed and the remainder is kept.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const line = frame.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        try {
          yield JSON.parse(line.slice(5).trim()) as StreamEvent;
        } catch {
          continue;
        }
      }
    }
  } finally {
    // Runs on early return too, so abandoning the generator does not leak the
    // connection.
    reader.releaseLock();
  }
}
