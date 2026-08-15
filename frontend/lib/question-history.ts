const STORAGE_KEY = "rag-eval.question-history.v1";

/**
 * How many past questions are kept.
 *
 * Capped because localStorage is a fixed budget shared with everything else on
 * the origin, and an uncapped list would grow until a write throws — at which
 * point the failure surfaces somewhere unrelated.
 */
export const HISTORY_LIMIT = 10;

/**
 * Past questions, newest first, persisted in the browser.
 *
 * Every entry point swallows its errors and degrades to "no history". Storage
 * is genuinely unavailable in several ordinary situations — Safari private
 * browsing throws on access, quota can be exhausted, the key can hold whatever
 * a previous version of this code wrote — and none of them are worth taking the
 * query page down for. History is a convenience; the input works without it.
 *
 * The questions stay in the browser and are never sent anywhere. `clear()`
 * exists so a user on a shared machine can remove them.
 */
export function readHistory(): string[] {
  const raw = safely(() => window.localStorage.getItem(STORAGE_KEY));
  if (!raw) return [];

  const parsed = safely(() => JSON.parse(raw) as unknown);
  if (!Array.isArray(parsed)) return [];

  // Filter rather than trust: the key may hold an older shape, or something
  // another script wrote.
  return parsed
    .filter((entry): entry is string => typeof entry === "string" && entry.trim() !== "")
    .slice(0, HISTORY_LIMIT);
}

/** Add a question, most recent first, without duplicating it. */
export function addToHistory(question: string): string[] {
  const trimmed = question.trim();
  if (!trimmed) return readHistory();

  // Case-insensitive dedupe with move-to-front: asking the same thing twice
  // should promote the entry, not create a second one.
  const withoutDuplicate = readHistory().filter(
    (entry) => entry.toLowerCase() !== trimmed.toLowerCase(),
  );
  const next = [trimmed, ...withoutDuplicate].slice(0, HISTORY_LIMIT);

  safely(() => window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next)));
  notify();
  // The in-memory list is returned even if the write failed, so the current
  // session still behaves correctly when storage is unavailable.
  return next;
}

export function clearHistory(): void {
  safely(() => window.localStorage.removeItem(STORAGE_KEY));
  notify();
}

/** Runs a storage operation, treating any failure as "storage is unavailable". */
function safely<T>(operation: () => T): T | null {
  if (typeof window === "undefined") return null;
  try {
    return operation();
  } catch {
    return null;
  }
}

/* -------------------------------------------------------------------------- */
/* Store                                                                      */
/*                                                                            */
/* localStorage is state this app does not own: another tab can change it.    */
/* Exposing it as an external store lets React subscribe properly instead of  */
/* copying it into component state after mount.                               */
/* -------------------------------------------------------------------------- */

const listeners = new Set<() => void>();

/**
 * The last parsed snapshot, kept so repeated reads return the same array.
 *
 * `useSyncExternalStore` re-renders whenever the snapshot is referentially
 * different, and `readHistory` builds a fresh array every call — returning it
 * directly would loop forever. The raw string is the cache key: if it has not
 * changed, neither has the parse.
 */
let cachedRaw: string | null = null;
let cachedSnapshot: string[] = [];

const EMPTY: string[] = [];

export function subscribeToHistory(onChange: () => void): () => void {
  listeners.add(onChange);
  // 'storage' fires only in *other* tabs, which is exactly what this app cannot
  // observe on its own; same-tab writes notify through `listeners`.
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function getHistorySnapshot(): string[] {
  const raw = safely(() => window.localStorage.getItem(STORAGE_KEY));
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedSnapshot = readHistory();
  }
  return cachedSnapshot;
}

/**
 * The server has no storage, so it renders no suggestions.
 *
 * A stable constant, not a fresh `[]`: a new array each call is a new snapshot,
 * and React would treat every render as a change.
 */
export function getHistoryServerSnapshot(): string[] {
  return EMPTY;
}

function notify() {
  for (const listener of listeners) listener();
}
