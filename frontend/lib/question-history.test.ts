import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  addToHistory,
  clearHistory,
  HISTORY_LIMIT,
  readHistory,
} from "./question-history";

const STORAGE_KEY = "rag-eval.question-history.v1";

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("readHistory", () => {
  it("is empty when nothing was ever stored", () => {
    expect(readHistory()).toEqual([]);
  });

  it.each([
    ["malformed JSON", "{not json"],
    ["a JSON object rather than an array", '{"a":1}'],
    ["a bare string", '"just a string"'],
    ["null", "null"],
  ])("degrades to empty for %s", (_label, stored) => {
    // The key can hold whatever a previous version — or another script — wrote.
    // A query page that white-screens on bad localStorage is worse than one
    // without suggestions.
    window.localStorage.setItem(STORAGE_KEY, stored);
    expect(readHistory()).toEqual([]);
  });

  it("drops entries of the wrong type without dropping the good ones", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(["keep", 42, null, "", "also"]),
    );
    expect(readHistory()).toEqual(["keep", "also"]);
  });

  it("returns nothing when storage itself throws", () => {
    // Safari in private mode throws on access rather than returning null.
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(readHistory()).toEqual([]);
  });
});

describe("addToHistory", () => {
  it("stores a question", () => {
    expect(addToHistory("what is ACID")).toEqual(["what is ACID"]);
    expect(readHistory()).toEqual(["what is ACID"]);
  });

  it("puts the newest first", () => {
    addToHistory("first");
    expect(addToHistory("second")).toEqual(["second", "first"]);
  });

  it("promotes a repeat instead of duplicating it", () => {
    addToHistory("a");
    addToHistory("b");
    expect(addToHistory("a")).toEqual(["a", "b"]);
  });

  it("treats case differences as the same question", () => {
    addToHistory("What Is ACID");
    expect(addToHistory("what is acid")).toEqual(["what is acid"]);
  });

  it("trims before storing", () => {
    expect(addToHistory("  spaced  ")).toEqual(["spaced"]);
  });

  it("ignores a blank question", () => {
    addToHistory("real");
    expect(addToHistory("   ")).toEqual(["real"]);
  });

  it("caps the list so storage cannot grow without bound", () => {
    for (let i = 0; i < HISTORY_LIMIT + 5; i += 1) addToHistory(`question ${i}`);

    const stored = readHistory();
    expect(stored).toHaveLength(HISTORY_LIMIT);
    // The oldest are the ones dropped.
    expect(stored[0]).toBe(`question ${HISTORY_LIMIT + 4}`);
    expect(stored).not.toContain("question 0");
  });

  it("still returns the updated list when the write fails", () => {
    // Quota exhaustion must not lose the entry for the current session.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    expect(addToHistory("unsaved")).toEqual(["unsaved"]);
  });
});

describe("clearHistory", () => {
  it("removes everything", () => {
    addToHistory("a");
    clearHistory();
    expect(readHistory()).toEqual([]);
  });

  it("does not throw when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(() => clearHistory()).not.toThrow();
  });
});
