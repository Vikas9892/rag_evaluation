import type { RetrieverMode } from "@/types/api";

/**
 * The query surface's state, as it appears in the URL.
 *
 * The URL is the source of truth rather than component state so a result is
 * reproducible: a link carries the question and the retrieval settings that
 * produced it. An evaluation tool whose results cannot be cited is a demo.
 */
export interface QueryParams {
  q: string;
  topK: number;
  retriever: RetrieverMode;
  reranker: boolean;
  corpus: string;
}

/**
 * Bounds copied from `QueryRequest` in api/schemas.py (`ge=1, le=20`).
 *
 * Duplicating them is deliberate. A hand-typed `?top_k=500` would otherwise
 * reach the API and come back 422, turning a typo into an error banner.
 *
 * Duplication across a language boundary drifts unless something checks it, so
 * `tests/test_api_contract.py` reads this file and fails if these numbers stop
 * matching the Pydantic field.
 */
export const TOP_K_MIN = 1;
export const TOP_K_MAX = 20;
export const TOP_K_DEFAULT = 5;

/**
 * Retrieval strategies, in the order the selector lists them.
 *
 * Declared here rather than imported from the generated schema because this
 * array is also the runtime validator for an untrusted URL, and a type cannot
 * check a string at runtime. `tests/test_api_contract.py` fails if it stops
 * matching the Literal the API accepts.
 */
export const RETRIEVERS = ["dense", "hybrid", "sparse"] as const;
export const RETRIEVER_DEFAULT: RetrieverMode = "dense";

/**
 * The benchmark corpus, and the default when the URL names none.
 *
 * Matches `DEFAULT_CORPUS_ID` in corpora/layout.py: a link with no corpus must
 * mean the same thing on both sides, or a shared result would silently be an
 * answer from a different set of documents.
 */
export const CORPUS_DEFAULT = "evaluation";

/**
 * Mirrors `_VALID_CORPUS_ID` in corpora/layout.py.
 *
 * The API refuses anything else, so an id that cannot match is not sent: the
 * check exists to keep a hand-edited URL from becoming a 422 banner. It is
 * also why a bad value falls back rather than being rewritten — a sanitised
 * corpus id would quietly answer from the wrong documents, which is worse
 * than ignoring the parameter.
 */
const VALID_CORPUS_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;

/**
 * Read params from a URL, repairing anything unusable.
 *
 * Never throws and never returns an out-of-range `topK`: these values come from
 * whatever someone pasted into the address bar, which is untrusted input, and a
 * malformed URL should degrade to a sane default rather than break the page.
 */
export function parseQueryParams(params: URLSearchParams): QueryParams {
  return {
    q: (params.get("q") ?? "").trim(),
    topK: parseTopK(params.get("top_k")),
    retriever: parseRetriever(params.get("retriever")),
    // Only an explicit "true" enables it. Anything else is off, so a mistyped
    // URL cannot silently add hundreds of milliseconds to every query.
    reranker: params.get("reranker") === "true",
    corpus: parseCorpus(params.get("corpus")),
  };
}

function parseCorpus(raw: string | null): string {
  const value = (raw ?? "").trim();
  return VALID_CORPUS_ID.test(value) ? value : CORPUS_DEFAULT;
}

function parseRetriever(raw: string | null): RetrieverMode {
  // An unknown value falls back rather than reaching the API, which would
  // answer 422 and surface a typo in the address bar as an error banner.
  return (RETRIEVERS as readonly string[]).includes(raw ?? "")
    ? (raw as RetrieverMode)
    : RETRIEVER_DEFAULT;
}

function parseTopK(raw: string | null): number {
  if (raw === null) return TOP_K_DEFAULT;

  // Number() would accept "  7  ", "0x10" and "1e1"; a strict digits-only test
  // keeps the URL to values a user could have meant.
  if (!/^\d+$/.test(raw.trim())) return TOP_K_DEFAULT;

  const value = Number(raw.trim());
  if (value < TOP_K_MIN) return TOP_K_MIN;
  if (value > TOP_K_MAX) return TOP_K_MAX;
  return value;
}

/**
 * Serialise params back to a query string.
 *
 * `top_k` is omitted when it is the default so the common URL stays short and
 * two links to the same question compare equal.
 */
export function buildQueryString({
  q,
  topK,
  retriever,
  reranker,
  corpus,
}: QueryParams): string {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (topK !== TOP_K_DEFAULT) params.set("top_k", String(topK));
  if (retriever !== RETRIEVER_DEFAULT) params.set("retriever", retriever);
  if (reranker) params.set("reranker", "true");
  if (corpus && corpus !== CORPUS_DEFAULT) params.set("corpus", corpus);
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}
