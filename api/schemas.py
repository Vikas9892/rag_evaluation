from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from config.settings import TOP_K

_QUERY_EXAMPLE = {
    "question": "What are the main components of a transformer architecture?",
    "top_k": 5,
}

_RESPONSE_EXAMPLE = {
    "answer": (
        "A transformer architecture consists of an encoder and a decoder, "
        "each built from stacked self-attention and feed-forward layers."
    ),
    "sources": [
        {
            "document_id": "attention_is_all_you_need",
            "chunk_id": "attention_is_all_you_need_chunk_3",
            "score": 0.9142,
        }
    ],
    "retrieval_latency_ms": 4.2,
    "generation_latency_ms": 1183.0,
    "total_latency_ms": 1187.2,
    "request_id": "3f8a1c20-d42b-4e7e-9b5f-abcdef012345",
}


class QueryRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={"example": _QUERY_EXAMPLE},
    )

    question: str = Field(
        ...,
        min_length=1,
        description="Natural-language question to answer using the knowledge base",
    )
    top_k: int = Field(
        default=TOP_K,
        ge=1,
        le=20,
        description="Number of chunks to retrieve (higher → more context, more latency)",
    )
    corpus_id: str = Field(
        default="evaluation",
        description=(
            "Which indexed collection to search. Retrieval is scoped to exactly one, "
            "so an uploaded document cannot be answered from another corpus."
        ),
    )
    reranker: bool = Field(
        default=False,
        description=(
            "Run the cross-encoder over the retrieved candidates. Far more accurate "
            "per candidate and far slower — one model forward pass each — so it is "
            "opt-in and the retriever fetches a wider candidate list when it is on."
        ),
    )
    retriever: Literal["dense", "sparse", "hybrid"] = Field(
        default="dense",
        description=(
            "Retrieval strategy. 'dense' is embedding similarity alone, 'sparse' is "
            "BM25 keyword matching alone, 'hybrid' fuses both with Reciprocal Rank "
            "Fusion. Comparing them is the point of the platform, so it is chosen "
            "per request rather than per deployment."
        ),
    )


class StageScore(BaseModel):
    """One retrieval stage's opinion of one chunk."""

    score: float = Field(
        description=(
            "The stage's own units — cosine similarity for dense, BM25 for sparse, "
            "an RRF sum for fusion. Not comparable across stages."
        )
    )
    rank: int = Field(description="1-indexed position within that stage's results")


class SourceScores(BaseModel):
    """Per-stage attribution for one chunk.

    A stage is null when it did not rank this chunk — either it did not run, or
    it ran and the chunk fell outside its candidate window. Which applies is
    resolved by `QueryResponse.retriever`, which reports what actually executed.

    Null never means "scored zero". BM25 scores zero for a chunk with no term
    overlap, and that is a measurement; absence is not.
    """

    dense: Optional[StageScore] = Field(default=None, description="Embedding similarity")
    sparse: Optional[StageScore] = Field(default=None, description="BM25 keyword match")
    fused: Optional[StageScore] = Field(default=None, description="Reciprocal Rank Fusion")
    reranker: Optional[StageScore] = Field(default=None, description="Cross-encoder rerank")


class SourceInfo(BaseModel):
    document_id: str = Field(description="Source document identifier")
    chunk_id: str = Field(description="Unique chunk identifier within the document")
    score: float = Field(description="Final score, in the units of the last stage to rank it")
    rank: int = Field(default=0, description="1-indexed final position")
    text: str = Field(default="", description="The retrieved chunk itself")
    metadata: Dict = Field(default_factory=dict, description="Chunk metadata, e.g. heading")
    scores: SourceScores = Field(
        default_factory=SourceScores,
        description="How each retrieval stage scored this chunk",
    )


class HealthResponse(BaseModel):
    """Liveness payload.

    Declared as a model rather than a bare dict so the OpenAPI schema carries a
    real shape: the frontend's TypeScript types are generated from it, and an
    untyped dict generates a type that says nothing.
    """

    model_config = ConfigDict(json_schema_extra={"example": {"status": "healthy"}})

    status: str = Field(description="Always 'healthy' while the process is serving")


class MetricsResponse(BaseModel):
    """Per-container counters accumulated since cold start."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_queries": 42,
                "avg_retrieval_ms": 36.2,
                "avg_generation_ms": 447.3,
                "errors": 0,
            }
        }
    )

    total_queries: int = Field(description="Queries answered since cold start")
    avg_retrieval_ms: float = Field(description="Mean retrieval latency (ms)")
    avg_generation_ms: float = Field(description="Mean LLM generation latency (ms)")
    errors: int = Field(description="Queries that raised before returning")


class PipelineStageInfo(BaseModel):
    """What one stage of the pipeline did.

    `skipped` means the stage did not run — a sparse-only query embeds nothing,
    and the cross-encoder reranker is not wired into the live path. The product
    spec requires these to render differently from stages that ran, and the
    diagram must never animate one that did not.

    `error` is part of the contract but is not emitted today: a stage that
    raises aborts the request, so no trace reaches the client.
    """

    name: Literal["embedding", "dense", "sparse", "fusion", "reranker", "generation"] = (
        Field(description="Stage identity, in data-flow order")
    )
    status: Literal["ok", "skipped", "error"] = Field(description="Whether the stage ran")
    latency_ms: float = Field(
        description="Measured duration; 0 for a skipped stage, which is an absence "
        "rather than a fast measurement"
    )
    candidates_in: Optional[int] = Field(
        default=None, description="Candidates entering the stage; null where inapplicable"
    )
    candidates_out: Optional[int] = Field(
        default=None, description="Candidates leaving the stage; null where inapplicable"
    )


class QueryResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": _RESPONSE_EXAMPLE})

    answer: str = Field(description="LLM-generated answer grounded in retrieved context")
    sources: List[SourceInfo] = Field(description="Retrieved chunks used to generate the answer")
    retrieval_latency_ms: float = Field(description="Time spent on FAISS search (ms)")
    generation_latency_ms: float = Field(description="Time spent on LLM call (ms)")
    total_latency_ms: float = Field(description="End-to-end latency (ms)")
    request_id: str = Field(description="UUID for request tracing in logs")
    corpus_id: str = Field(
        default="evaluation", description="The collection that was searched"
    )
    abstained: bool = Field(
        default=False,
        description=(
            "True when the model declined for lack of grounding, per the exact reply "
            "the system prompt demands. A compliance check, not an interpretation of "
            "the answer's meaning."
        ),
    )
    retriever: Literal["dense", "sparse", "hybrid"] = Field(
        default="hybrid",
        description=(
            "Which strategy ran. Needed to read `sources[].scores`: it tells a "
            "null stage that did not run apart from one that missed a chunk."
        ),
    )
    pipeline: List[PipelineStageInfo] = Field(
        default_factory=list,
        description="Every stage in data-flow order, including those that did not run",
    )


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------


class HealthCheck(BaseModel):
    """One dependency's verdict."""

    name: str = Field(description="Dependency checked")
    status: Literal["pass", "warn", "fail"] = Field(
        description="warn means degraded but serving — a missing API key breaks "
        "generation while retrieval keeps working"
    )
    detail: str = Field(description="What was found, in terms an operator can act on")


class DeepHealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        description="Worst of the individual checks"
    )
    checks: List[HealthCheck] = Field(description="Every dependency, including passing ones")


class ConfigResponse(BaseModel):
    """What this deployment is running, so the UI never hardcodes it."""

    embedding_model: str
    llm_model: str
    llm_temperature: float
    llm_max_tokens: int
    chunk_size: int
    chunk_overlap: int
    min_chunk_chars: int
    default_top_k: int
    max_context_chunks: int
    retrievers: List[str] = Field(description="Strategies this deployment accepts")
    indexed_chunks: int = Field(description="Chunks in the index")
    documents: int = Field(description="Distinct source documents behind them")
    reranker_enabled: bool = Field(
        description="Whether the cross-encoder runs by default; it does not, because it "
        "costs hundreds of milliseconds for a small MRR gain"
    )
    reranker_available: bool = Field(
        default=True, description="Whether a request may switch the cross-encoder on"
    )
    default_retriever: str = Field(
        default="dense", description="Strategy used when a request does not choose one"
    )


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class RetrievalMetrics(BaseModel):
    precision_at_k: float = Field(
        description="Structurally capped when a question has fewer relevant chunks "
        "than K: retrieving 5 for 1 relevant chunk caps this at 0.2"
    )
    recall_at_k: float = Field(description="Share of relevant chunks retrieved")
    hit_rate: float = Field(description="Questions with at least one relevant chunk retrieved")
    mrr: float = Field(description="Mean reciprocal rank of the first relevant chunk")
    avg_latency_ms: float = Field(description="Mean retrieval latency across the dataset")
    p50_latency_ms: float = Field(
        default=0.0, description="Median retrieval latency across the dataset"
    )
    p95_latency_ms: float = Field(
        default=0.0,
        description="95th-percentile retrieval latency. The mean hides the tail, "
        "and the tail is what a waiting user experiences.",
    )


class PerQuestionResult(BaseModel):
    id: int
    question: str
    hit: bool
    precision: float
    recall: float
    reciprocal_rank: float
    latency_ms: float
    retrieved_ids: List[str]
    expected_ids: List[str]


class EvaluationResponse(BaseModel):
    top_k: int
    retriever: Literal["dense", "sparse", "hybrid"]
    reranker: bool = False
    dataset_size: int
    cached: bool = Field(description="Whether this run was served from the in-process cache")
    metrics: RetrievalMetrics
    questions: List[PerQuestionResult]


class BenchmarkCell(BaseModel):
    retriever: Literal["dense", "sparse", "hybrid"]
    top_k: int
    reranker: bool = False
    metrics: RetrievalMetrics


class BenchmarkResponse(BaseModel):
    dataset_size: int
    cells: List[BenchmarkCell]
    pending: int = Field(
        default=0,
        description=(
            "Configurations not yet measured. The sweep takes minutes on a cold cache, "
            "so each call does a bounded amount of work and leaves the rest; ask again "
            "to continue. Zero means the matrix is complete."
        ),
    )
    cached: bool
    discriminating: bool = Field(
        description="False when every configuration scores identically, which means the "
        "corpus is too small for the comparison to say anything about the retrievers"
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    """One uploaded document and where it is in the pipeline."""

    document_id: str
    corpus_id: str
    filename: str = Field(description="Sanitised for display; never a filesystem path")
    content_type: str
    size_bytes: int
    status: Literal[
        "UPLOADING", "QUEUED", "PARSING", "CHUNKING", "EMBEDDING", "INDEXING", "READY", "FAILED"
    ] = Field(description="The worker's actual stage, not an invented progress step")
    progress: float = Field(
        description="0 to 1 through the pipeline. A failed document reports 0, because a "
        "bar stopped part way reads as still working."
    )
    chunk_count: int = Field(description="Chunks indexed; 0 until the document is READY")
    error: Optional[str] = Field(
        default=None, description="Why indexing failed, in terms the uploader can act on"
    )
    created_at: str
    updated_at: str


class DocumentCreateResponse(BaseModel):
    """Accepted for indexing — not yet indexed."""

    document_id: str
    job_id: str
    corpus_id: str
    status: str = Field(description="QUEUED; indexing happens on a worker")
    filename: str
    duplicate_of: Optional[str] = Field(
        default=None,
        description=(
            "Set when a byte-identical file is already in this corpus. Nothing is "
            "stored or indexed again and `document_id` is the existing document: "
            "two copies of the same text would occupy two top-K slots and answer "
            "the same question twice. `job_id` is empty because no work was queued."
        ),
    )


class DocumentListResponse(BaseModel):
    corpus_id: Optional[str] = None
    documents: List[DocumentResponse]


class CorpusSummary(BaseModel):
    """One collection, and whether it can be searched."""

    corpus_id: str
    documents: int
    chunks: int
    ready: bool = Field(description="Whether an index exists to query")
    is_evaluation: bool = Field(
        description="The corpus the benchmark measures. Kept separate so uploads "
        "cannot move a published metric."
    )


class CorpusListResponse(BaseModel):
    corpora: List[CorpusSummary]


class QueueStatusResponse(BaseModel):
    """What the queue is, and what it does not guarantee."""

    backend: Literal["in-process", "redis"]
    durable: bool = Field(
        description="False for the in-process queue: jobs are lost if the API restarts"
    )
    workers: int
    note: str


# ---------------------------------------------------------------------------
# Settings taxonomy
# ---------------------------------------------------------------------------


class SettingDescriptor(BaseModel):
    """One setting, and when it takes effect.

    The distinction is the point. Top-K changes the next answer; chunk size
    changes nothing until every document is re-embedded and re-indexed. A UI
    that shows them side by side as equivalent sliders promises something the
    system cannot do, so the API states the scope rather than leaving the
    frontend to guess.
    """

    key: str
    label: str
    value: str = Field(description="The value in force, as text for display")
    scope: Literal["query", "indexing", "generation"] = Field(
        description=(
            "query: applies to the next request. indexing: fixed when a document was "
            "indexed. generation: applies to the next answer."
        )
    )
    requires_reindex: bool = Field(
        description="True when changing this invalidates every existing index"
    )
    editable_per_request: bool = Field(
        description="True when a single request may override it"
    )
    note: Optional[str] = None


class SettingsResponse(BaseModel):
    groups: Dict[str, List[SettingDescriptor]] = Field(
        description="Settings by area: retrieval, generation, indexing"
    )
