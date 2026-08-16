import type { BenchmarkCell } from "@/types/api";

export const SORT_KEYS = [
  "configuration",
  "top_k",
  "precision_at_k",
  "recall_at_k",
  "mrr",
  "hit_rate",
  "avg_latency_ms",
] as const;

export type SortKey = (typeof SORT_KEYS)[number];
export type SortDirection = "asc" | "desc";

export interface Sort {
  key: SortKey;
  direction: SortDirection;
}

export function configurationLabel(cell: BenchmarkCell): string {
  return `${cell.retriever} · top-${cell.top_k}${cell.reranker ? " · reranked" : ""}`;
}

/**
 * The direction a column should open in when it is first clicked.
 *
 * Quality metrics open descending because the question is always "which is
 * best"; latency and K open ascending because for those, less is the good
 * direction. Opening every column ascending would make the first click on MRR
 * show the worst configuration.
 */
export function defaultDirection(key: SortKey): SortDirection {
  return key === "avg_latency_ms" || key === "top_k" || key === "configuration"
    ? "asc"
    : "desc";
}

export function nextSort(current: Sort, key: SortKey): Sort {
  if (current.key !== key) return { key, direction: defaultDirection(key) };
  return { key, direction: current.direction === "asc" ? "desc" : "asc" };
}

function valueFor(cell: BenchmarkCell, key: SortKey): number | string {
  if (key === "configuration") return configurationLabel(cell);
  if (key === "top_k") return cell.top_k;
  return cell.metrics[key];
}

/**
 * Sort a copy, never the array itself.
 *
 * The cells come from the query cache; sorting in place would reorder them for
 * every other reader of that cache, including the chart above the table.
 */
export function sortCells(cells: readonly BenchmarkCell[], sort: Sort): BenchmarkCell[] {
  const factor = sort.direction === "asc" ? 1 : -1;
  return [...cells].sort((a, b) => {
    const left = valueFor(a, sort.key);
    const right = valueFor(b, sort.key);
    const comparison =
      typeof left === "string" && typeof right === "string"
        ? left.localeCompare(right)
        : Number(left) - Number(right);
    // Ties broken by label so the order is total and the table does not
    // reshuffle equal rows between renders.
    return comparison !== 0
      ? comparison * factor
      : configurationLabel(a).localeCompare(configurationLabel(b));
  });
}

/**
 * How much MRR two configurations must differ by before the gap is called real.
 *
 * On 53 labelled questions one question moving from rank 2 to rank 1 shifts MRR
 * by about 0.009. Treating anything smaller than this as a difference would be
 * reading noise, so configurations inside the band are reported as tied.
 */
export const MRR_TOLERANCE = 0.02;

export interface Recommendation {
  /** Highest MRR outright. */
  best: BenchmarkCell;
  /** The cheapest configuration that is not meaningfully worse than `best`. */
  value: BenchmarkCell;
  /** Whether those are the same configuration. */
  agreed: boolean;
  /** What `best` costs over `value`, in latency and in MRR. */
  extraLatencyMs: number;
  extraMrr: number;
  tolerance: number;
}

/**
 * Which configuration to ship.
 *
 * Not simply the highest MRR: the reranked configurations win on quality and
 * cost hundreds of milliseconds, which is a trade to make deliberately rather
 * than a winner to crown. So this reports two — the best outright, and the
 * fastest one that is within `MRR_TOLERANCE` of it — and states what the
 * difference costs. When they are the same configuration there is no trade to
 * make, and it says that instead.
 */
export function recommend(cells: readonly BenchmarkCell[]): Recommendation | null {
  if (cells.length === 0) return null;

  const best = [...cells].sort((a, b) => b.metrics.mrr - a.metrics.mrr)[0];
  // The epsilon is for binary floating point, not for the statistics: MRR
  // values are decimals that do not represent exactly, so a gap of precisely
  // the tolerance subtracts to 0.020000000000000018 and a strict comparison
  // would drop the very configuration the tolerance exists to keep.
  const withinTolerance = cells.filter(
    (cell) => best.metrics.mrr - cell.metrics.mrr <= MRR_TOLERANCE + 1e-9,
  );
  const value = [...withinTolerance].sort(
    (a, b) => a.metrics.avg_latency_ms - b.metrics.avg_latency_ms,
  )[0];

  return {
    best,
    value,
    agreed: configurationLabel(best) === configurationLabel(value),
    extraLatencyMs: best.metrics.avg_latency_ms - value.metrics.avg_latency_ms,
    extraMrr: best.metrics.mrr - value.metrics.mrr,
    tolerance: MRR_TOLERANCE,
  };
}
