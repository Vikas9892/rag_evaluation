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
    retriever: Literal["dense", "sparse", "hybrid"] = Field(
        default="hybrid",
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
