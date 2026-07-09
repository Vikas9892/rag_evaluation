from typing import List

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


class SourceInfo(BaseModel):
    document_id: str = Field(description="Source document identifier")
    chunk_id: str = Field(description="Unique chunk identifier within the document")
    score: float = Field(description="Cosine-similarity score in [0, 1]")


class QueryResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": _RESPONSE_EXAMPLE})

    answer: str = Field(description="LLM-generated answer grounded in retrieved context")
    sources: List[SourceInfo] = Field(description="Retrieved chunks used to generate the answer")
    retrieval_latency_ms: float = Field(description="Time spent on FAISS search (ms)")
    generation_latency_ms: float = Field(description="Time spent on LLM call (ms)")
    total_latency_ms: float = Field(description="End-to-end latency (ms)")
    request_id: str = Field(description="UUID for request tracing in logs")
