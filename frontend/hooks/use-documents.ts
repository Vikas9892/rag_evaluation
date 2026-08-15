"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteDocument,
  getCorpora,
  getDocuments,
  getQueueStatus,
  uploadDocument,
} from "@/services/api";
import type { DocumentResponse } from "@/types/api";

/** Statuses from which nothing further happens without another request. */
const TERMINAL = new Set(["READY", "FAILED"]);

export const documentsKey = (corpusId?: string) =>
  ["documents", corpusId ?? "all"] as const;

/**
 * Documents in a corpus, polled only while something is still indexing.
 *
 * Indexing is asynchronous and can take a minute, so the list has to move on
 * its own. Polling stops as soon as everything is READY or FAILED — a fixed
 * interval would keep asking forever about a corpus nobody is changing.
 */
export function useDocuments(corpusId?: string) {
  return useQuery({
    queryKey: documentsKey(corpusId),
    queryFn: ({ signal }) => getDocuments(corpusId, signal),
    refetchInterval: (query) => {
      const documents = query.state.data?.documents ?? [];
      return documents.some((d) => !TERMINAL.has(d.status)) ? 1500 : false;
    },
  });
}

export function useCorpora() {
  return useQuery({
    queryKey: ["corpora"],
    queryFn: ({ signal }) => getCorpora(signal),
    staleTime: 15_000,
  });
}

export function useQueueStatus() {
  return useQuery({
    queryKey: ["queue"],
    queryFn: ({ signal }) => getQueueStatus(signal),
    staleTime: 5 * 60_000,
  });
}

/**
 * Upload a file.
 *
 * A mutation rather than a query: it has a side effect, it is triggered by a
 * person, and it must not be retried automatically — a retried upload would
 * either duplicate the document or waste a second round trip discovering it is
 * a duplicate.
 */
export function useUploadDocument(corpusId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { file: File; chunkSize?: number; chunkOverlap?: number }) =>
      uploadDocument(input.file, corpusId, {
        chunkSize: input.chunkSize,
        chunkOverlap: input.chunkOverlap,
      }),
    retry: false,
    onSuccess: () => {
      // The new document is QUEUED; refetching starts the polling that follows
      // it to READY.
      void client.invalidateQueries({ queryKey: documentsKey(corpusId) });
      void client.invalidateQueries({ queryKey: documentsKey() });
      void client.invalidateQueries({ queryKey: ["corpora"] });
    },
  });
}

export function useDeleteDocument(corpusId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => deleteDocument(documentId),
    retry: false,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: documentsKey(corpusId) });
      void client.invalidateQueries({ queryKey: documentsKey() });
      void client.invalidateQueries({ queryKey: ["corpora"] });
      // Deleting rebuilds the index, so a cached answer may cite chunks that
      // no longer exist.
      void client.invalidateQueries({ queryKey: ["rag-query"] });
    },
  });
}

export function isIndexing(document: DocumentResponse): boolean {
  return !TERMINAL.has(document.status);
}
