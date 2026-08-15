import type { components } from "./api.generated";

/**
 * Named aliases over the generated OpenAPI schema.
 *
 * The generated file is regenerated wholesale by `npm run gen:api`, so nothing
 * imports from it directly except this module. If the backend renames or
 * removes a schema, the break surfaces here — one file — instead of scattered
 * across every component that happened to reference the generated path.
 */
type Schemas = components["schemas"];

export type HealthResponse = Schemas["HealthResponse"];
export type MetricsResponse = Schemas["MetricsResponse"];
export type QueryRequest = Schemas["QueryRequest"];
export type QueryResponse = Schemas["QueryResponse"];
export type SourceInfo = Schemas["SourceInfo"];

/** One event from the /stream SSE endpoint. */
export type StreamEvent =
  | { type: "sources"; data: StreamSource[] }
  | { type: "token"; data: string }
  | { type: "done"; data: StreamDone }
  | { type: "error"; data: string };

/**
 * The stream's closing payload: what POST /query returns in its body, plus
 * time-to-first-token, which only the streaming path can measure.
 */
export interface StreamDone {
  request_id: string;
  retrieval_latency_ms: number;
  generation_latency_ms: number;
  total_latency_ms: number;
  /** null when the model produced no tokens — not the same as arriving in 0 ms. */
  first_token_latency_ms: number | null;
}

/**
 * Source metadata as it appears in the stream's first event.
 *
 * Hand-written because /stream returns text/event-stream: FastAPI cannot
 * describe the event payloads in OpenAPI, so there is nothing to generate from.
 * This type is a contract with api/routers/stream.py and must be updated with it.
 */
export interface StreamSource {
  document_id: string;
  chunk_id: string;
  score: number;
}
