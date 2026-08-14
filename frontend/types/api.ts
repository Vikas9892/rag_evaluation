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
  | { type: "done" }
  | { type: "error"; data: string };

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
