from typing import List

from pydantic import BaseModel, ConfigDict, Field

from config.settings import TOP_K


class QueryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(..., min_length=1, description="Question to answer")
    top_k: int = Field(
        default=TOP_K, ge=1, le=20, description="Number of chunks to retrieve"
    )


class SourceInfo(BaseModel):
    document_id: str
    chunk_id: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceInfo]
    retrieval_latency_ms: float
    generation_latency_ms: float
    total_latency_ms: float
    request_id: str
