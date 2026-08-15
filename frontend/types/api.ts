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
  /** Which strategy actually ran — the authority for reading a null stage. */
  retriever: RetrieverMode;
  retrieval_latency_ms: number;
  generation_latency_ms: number;
  total_latency_ms: number;
  /** null when the model produced no tokens — not the same as arriving in 0 ms. */
  first_token_latency_ms: number | null;
}

/**
 * Source metadata as it appears in the stream's first event.
 *
 * The stream and POST /query build sources with the same serialiser
 * (`source_payload` in services/rag_service.py), so this is the generated
 * `SourceInfo` rather than a parallel hand-written shape that could drift from
 * it. `tests/test_api_contract.py` fails if the two ever stop matching.
 */
export type StreamSource = SourceInfo;

/** Which retrieval strategy to run, or which one did. */
export type RetrieverMode = NonNullable<QueryRequest["retriever"]>;
