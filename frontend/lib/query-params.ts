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
  };
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
export function buildQueryString({ q, topK }: QueryParams): string {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (topK !== TOP_K_DEFAULT) params.set("top_k", String(topK));
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}
