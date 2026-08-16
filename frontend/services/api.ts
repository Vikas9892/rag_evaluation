import type {
  BenchmarkResponse,
  CorpusSummary,
  DocumentCreateResponse,
  DocumentResponse,
  QueueStatusResponse,
  SettingsResponse,
  ConfigResponse,
  DeepHealthResponse,
  EvaluationResponse,
  HealthResponse,
  MetricsResponse,
  QueryResponse,
  RetrieverMode,
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
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

/**
 * Turn FastAPI's validation payload into a sentence.
 *
 * A 422 body is a list of objects, not a string, so rendering it directly puts
 * "[object Object]" in front of the user. The field and the reason are both in
 * there — "top_k: Input should be less than or equal to 20" is something a
 * person can act on, where "1 validation error(s)" is not.
 */
function summariseValidation(detail: readonly unknown[]): string | undefined {
  const messages = detail
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const { loc, msg } = item as { loc?: unknown; msg?: unknown };
      if (typeof msg !== "string") return null;
      // loc is ["body", "top_k"] or ["query", "chunk_size"]; the field is the
      // last segment, and the first only says where it arrived.
      const field = Array.isArray(loc)
        ? loc
            .filter(
              (part) => typeof part === "string" && part !== "body" && part !== "query",
            )
            .pop()
        : undefined;
      return field ? `${field}: ${msg}` : msg;
    })
    .filter((message): message is string => message !== null);

  // An unrecognised shape falls back to the count rather than to nothing: the
  // user still learns the request was rejected for being malformed.
  if (messages.length === 0)
    return detail.length ? `${detail.length} validation error(s)` : undefined;
  return messages.join("; ");
}

/** Pull FastAPI's `detail` out of an error body without assuming it is there. */
async function readDetail(response: Response): Promise<string | undefined> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const { detail } = body as { detail: unknown };
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) return summariseValidation(detail);
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

export function getConfig(signal?: AbortSignal): Promise<ConfigResponse> {
  return request<ConfigResponse>("/config", { signal }, 5_000);
}

export function getDeepHealth(signal?: AbortSignal): Promise<DeepHealthResponse> {
  return request<DeepHealthResponse>("/health/deep", { signal }, 10_000);
}

export function getEvaluation(
  topK: number,
  retriever: RetrieverMode,
  signal?: AbortSignal,
): Promise<EvaluationResponse> {
  // Longer deadline than a page load would normally allow: an uncached run
  // embeds every question in the dataset. Subsequent runs are served from the
  // API's cache and return immediately.
  return request<EvaluationResponse>(
    `/evaluation?top_k=${topK}&retriever=${retriever}`,
    { signal },
    60_000,
  );
}

export function getBenchmarks(signal?: AbortSignal): Promise<BenchmarkResponse> {
  // Nine configurations over the whole dataset on a cold cache.
  return request<BenchmarkResponse>("/benchmarks", { signal }, 180_000);
}

export function getCorpora(signal?: AbortSignal): Promise<{ corpora: CorpusSummary[] }> {
  return request<{ corpora: CorpusSummary[] }>("/corpora", { signal }, 10_000);
}

export function getDocuments(
  corpusId?: string,
  signal?: AbortSignal,
): Promise<{ documents: DocumentResponse[] }> {
  const query = corpusId ? `?corpus_id=${encodeURIComponent(corpusId)}` : "";
  return request<{ documents: DocumentResponse[] }>(
    `/documents${query}`,
    { signal },
    10_000,
  );
}

export function getDocumentStatus(
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentResponse> {
  return request<DocumentResponse>(
    `/documents/${encodeURIComponent(documentId)}/status`,
    { signal },
    10_000,
  );
}

export function deleteDocument(documentId: string): Promise<unknown> {
  return request<unknown>(
    `/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
    30_000,
  );
}

export function getQueueStatus(signal?: AbortSignal): Promise<QueueStatusResponse> {
  return request<QueueStatusResponse>("/queue", { signal }, 5_000);
}

export function getSettings(signal?: AbortSignal): Promise<SettingsResponse> {
  return request<SettingsResponse>("/settings", { signal }, 10_000);
}

/**
 * Upload one file.
 *
 * Deliberately not routed through `request`: that helper sets a JSON
 * content-type, and a multipart body needs the browser to set its own boundary.
 * The deadline is long because the request carries the whole file.
 */
export async function uploadDocument(
  file: File,
  corpusId: string,
  options: { chunkSize?: number; chunkOverlap?: number } = {},
): Promise<DocumentCreateResponse> {
  const params = new URLSearchParams({ corpus_id: corpusId });
  if (options.chunkSize) params.set("chunk_size", String(options.chunkSize));
  if (options.chunkOverlap !== undefined) {
    params.set("chunk_overlap", String(options.chunkOverlap));
  }

  const body = new FormData();
  body.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/documents?${params}`, {
      method: "POST",
      body,
    });
  } catch (cause) {
    throw new ApiError("network", "The upload never reached the API", { cause });
  }

  if (!response.ok) {
    throw new ApiError(
      kindForStatus(response.status),
      `Upload failed with ${response.status}`,
      { status: response.status, detail: await readDetail(response) },
    );
  }
  return (await response.json()) as DocumentCreateResponse;
}

export function postQuery(
  question: string,
  options: QueryOptions = {},
): Promise<QueryResponse> {
  return request<QueryResponse>("/query", {
    method: "POST",
    body: JSON.stringify(requestBody(question, options)),
    signal: options.signal,
  });
}

/** Omits defaults so the request carries only what the caller chose. */
/**
 * What to ask, and of which corpus.
 *
 * An options object rather than positional arguments: `question, topK, signal,
 * retriever, reranker, corpus` is six parameters of which four are optional and
 * two are booleans-or-strings, and transposing any pair of them type-checks.
 */
export interface QueryOptions {
  topK?: number;
  retriever?: RetrieverMode;
  reranker?: boolean;
  /** Omitted means the API's default corpus, which is the benchmark set. */
  corpusId?: string;
  signal?: AbortSignal;
}

function requestBody(question: string, options: QueryOptions) {
  const { topK, retriever, reranker, corpusId } = options;
  return {
    question,
    ...(topK === undefined ? {} : { top_k: topK }),
    ...(retriever === undefined ? {} : { retriever }),
    ...(reranker ? { reranker: true } : {}),
    ...(corpusId === undefined ? {} : { corpus_id: corpusId }),
  };
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
  options: QueryOptions = {},
): AsyncGenerator<StreamEvent> {
  const { signal } = options;
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody(question, options)),
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
