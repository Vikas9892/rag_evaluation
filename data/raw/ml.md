# Embeddings and Retrieval — Core Notes

## Embeddings

An embedding maps text to a vector of floating-point numbers such that semantically similar
text lands nearby. The dimensionality is fixed by the model — BAAI/bge-small-en-v1.5 produces
384 dimensions — regardless of how long the input is.

Similarity is measured by cosine similarity, the cosine of the angle between two vectors, which
ignores magnitude and compares direction. Normalising vectors to unit length makes the dot
product equal to cosine similarity, which is why vector stores normalise on insert.

An embedding model has a context window. Text longer than it is truncated silently, so a chunk
that exceeds the window loses its tail without any error being raised.

## Chunking

Retrieval operates on chunks, not documents, because an embedding of a whole document averages
every topic in it into one vector that is close to nothing in particular.

Chunk size trades recall against precision. Large chunks carry more context and dilute the
signal; small chunks are sharply focused and may omit the sentence that makes the answer
meaningful.

Overlap repeats a window of text between neighbouring chunks so that an answer spanning a
boundary survives in at least one of them.

Splitting on structure — headings, then paragraphs, then sentences — beats splitting at a fixed
character count, because a chunk that aligns to one section is about one thing. A purely
positional split cuts mid-sentence and produces chunks that match nothing.

## Dense Retrieval

Dense retrieval embeds the query and finds the nearest chunk vectors. It matches meaning rather
than wording, so it answers a question phrased differently from the source text.

Its weakness is exact tokens: a rare identifier, an error code or a product name may be
represented poorly, and a dense retriever can miss a chunk that contains the literal string
being searched for.

## Sparse Retrieval and BM25

Sparse retrieval scores by term overlap. BM25 weights a term by how often it appears in the
chunk, damped so repetition saturates, and by how rare it is across the corpus.

The inverse document frequency term is what makes a rare word decisive and a common one nearly
worthless. On a very small corpus this becomes unstable: a term appearing in half the documents
carries almost no information and BM25 scores it near zero.

BM25 also normalises for length, so a long chunk does not outrank a short one merely by
containing more words.

## Hybrid Retrieval and Fusion

Hybrid retrieval runs dense and sparse together and combines the rankings, on the theory that
their failures are uncorrelated — one matches meaning, the other matches tokens.

Reciprocal Rank Fusion combines them without comparing incomparable scores. Each chunk scores
the sum over retrievers of one over a constant k plus its rank in that retriever, with k
typically 60. Because it uses ranks rather than raw scores, a cosine similarity and a BM25
score never have to be placed on the same scale.

Fusion is not automatically an improvement. It gives each retriever an equal vote, so if one is
substantially worse on a corpus it drags the combined ranking down. Whether hybrid beats its
own better half is an empirical question and must be measured, not assumed.

## Reranking

A cross-encoder reranker takes the query and a candidate chunk together and scores their
relevance directly, rather than comparing two independently produced vectors. It is far more
accurate and far slower, because it runs one forward pass per candidate instead of one per
query.

The standard arrangement is retrieve-then-rerank: a cheap retriever produces a wide candidate
list and the reranker reorders only the top few dozen. Reranking the whole corpus would be
accurate and unusable.

## Evaluating Retrieval

Precision@K is the fraction of the K retrieved chunks that are relevant. When a question has
one relevant chunk and K is five, precision cannot exceed 0.2, so a low value may be arithmetic
rather than a failure.

Recall@K is the fraction of relevant chunks that were retrieved, and is the metric to read when
relevant chunks are few.

Mean Reciprocal Rank averages one over the rank of the first relevant chunk. It rewards putting
the right answer first and is insensitive to what follows.

Hit rate is the fraction of questions with at least one relevant chunk retrieved. It is coarse
and useful as a floor: a hit rate below one means some questions retrieve nothing useful at all.

## Ground Truth

Evaluation metrics require labelled data, so they cannot be computed for an arbitrary user
question. This is the reason accuracy metrics and ad-hoc queries belong on separate surfaces.

Ground truth anchored to positions is fragile. Labels stored as chunk indices silently point at
different text the moment the corpus is re-chunked, and every metric continues to compute
without error. Anchoring labels to content spans and resolving them against the live index
turns that silent corruption into a loud failure.
