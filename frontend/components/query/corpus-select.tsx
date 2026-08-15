"use client";

import { InlineField } from "@/components/ui/inline-field";
import { NativeSelect } from "@/components/ui/native-select";
import { useCorpora } from "@/hooks/use-documents";
import { CORPUS_DEFAULT } from "@/lib/query-params";

/**
 * Which set of documents to ask.
 *
 * The list comes from the API rather than a constant, because a corpus exists
 * as soon as someone uploads a file — a hard-coded list would go stale the
 * moment the workspace is used.
 *
 * The current value is always offered, even when the fetch has not landed or
 * has failed. A link carrying `?corpus=workspace` must not silently fall back
 * to the benchmark corpus while the list loads: that would answer from the
 * wrong documents and look like a retrieval failure.
 */
export function CorpusSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (corpusId: string) => void;
}) {
  const { data } = useCorpora();

  const available = data?.corpora ?? [];
  const options = available.some((corpus) => corpus.corpus_id === value)
    ? available.map((corpus) => ({
        id: corpus.corpus_id,
        label: labelFor(corpus.corpus_id, corpus.documents, corpus.chunks),
      }))
    : [{ id: value, label: labelFor(value) }, ...available.map(toOption)];

  return (
    <InlineField htmlFor="corpus" label="Corpus">
      <NativeSelect
        id="corpus"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-52"
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </NativeSelect>
    </InlineField>
  );
}

function toOption(corpus: { corpus_id: string; documents: number; chunks: number }) {
  return {
    id: corpus.corpus_id,
    label: labelFor(corpus.corpus_id, corpus.documents, corpus.chunks),
  };
}

function labelFor(corpusId: string, documents?: number, chunks?: number): string {
  const name = corpusId === CORPUS_DEFAULT ? "evaluation (benchmark)" : corpusId;
  // The evaluation index is built offline, so it has no document records to
  // count. Reporting "0 documents" for the corpus every metric comes from
  // would read as broken.
  if (!documents || !chunks) return name;
  return `${name} — ${chunks} chunks`;
}
