"use client";

import { useCallback, useSyncExternalStore } from "react";

import {
  addToHistory,
  clearHistory,
  getHistorySnapshot,
  getHistoryServerSnapshot,
  subscribeToHistory,
} from "@/lib/question-history";

/**
 * Past questions, for the input's suggestions.
 *
 * Subscribed to rather than copied into state. localStorage is not this app's
 * state — it does not exist on the server, and another tab can change it — so
 * the server snapshot is empty, the client's is read on hydration, and a write
 * in either tab re-renders whoever is listening.
 */
export function useQuestionHistory() {
  const history = useSyncExternalStore(
    subscribeToHistory,
    getHistorySnapshot,
    getHistoryServerSnapshot,
  );

  const remember = useCallback((question: string) => {
    addToHistory(question);
  }, []);

  const forget = useCallback(() => {
    clearHistory();
  }, []);

  return { history, remember, forget };
}
