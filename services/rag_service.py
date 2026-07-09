import json
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from config.logging_config import get_logger
from config.settings import TOP_K
from generation.generator import BaseGenerator
from generation.prompt_builder import PromptBuilder
from retrieval.ranking import RetrievalResult
from retrieval.retriever import Retriever

logger = get_logger(__name__)


@dataclass
class RAGResponse:
    answer: str
    sources: List[RetrievalResult]
    retrieval_latency_ms: float
    generation_latency_ms: float
    request_id: str


@dataclass
class _ServiceMetrics:
    total_queries: int = field(default=0)
    total_retrieval_ms: float = field(default=0.0)
    total_generation_ms: float = field(default=0.0)
    errors: int = field(default=0)

    @property
    def avg_retrieval_ms(self) -> float:
        return self.total_retrieval_ms / self.total_queries if self.total_queries else 0.0

    @property
    def avg_generation_ms(self) -> float:
        return self.total_generation_ms / self.total_queries if self.total_queries else 0.0

    def as_dict(self) -> dict:
        return {
            "total_queries": self.total_queries,
            "avg_retrieval_ms": round(self.avg_retrieval_ms, 1),
            "avg_generation_ms": round(self.avg_generation_ms, 1),
            "errors": self.errors,
        }


class RAGService:
    """Orchestrates retrieval + prompt building + LLM generation.

    Owns no I/O — all I/O is delegated to injected components, which makes
    the service trivially testable with mock dependencies.
    """

    def __init__(
        self,
        retriever: Retriever,
        generator: BaseGenerator,
        builder: PromptBuilder,
        default_top_k: int = TOP_K,
    ) -> None:
        self._retriever = retriever
        self._generator = generator
        self._builder = builder
        self._default_top_k = default_top_k
        self._metrics = _ServiceMetrics()

    # ------------------------------------------------------------------
    # Core operation
    # ------------------------------------------------------------------

    def answer(self, question: str, top_k: Optional[int] = None) -> RAGResponse:
        request_id = str(uuid.uuid4())
        k = top_k if top_k is not None else self._default_top_k

        try:
            t0 = time.perf_counter()
            results = self._retriever.retrieve(question, top_k=k)
            retrieval_ms = (time.perf_counter() - t0) * 1000

            prompt = self._builder.build(question, results)
            response = self._generator.generate(prompt, results)

            self._metrics.total_queries += 1
            self._metrics.total_retrieval_ms += retrieval_ms
            self._metrics.total_generation_ms += response.latency_ms
        except Exception:
            self._metrics.errors += 1
            raise

        logger.info(
            json.dumps({
                "event": "query",
                "request_id": request_id,
                "question_len": len(question),
                "chunks_retrieved": len(results),
                "retrieval_ms": round(retrieval_ms, 1),
                "generation_ms": round(response.latency_ms, 1),
                "total_ms": round(retrieval_ms + response.latency_ms, 1),
                "tokens": response.total_tokens,
            })
        )

        return RAGResponse(
            answer=response.answer,
            sources=results,
            retrieval_latency_ms=retrieval_ms,
            generation_latency_ms=response.latency_ms,
            request_id=request_id,
        )

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict:
        return self._metrics.as_dict()
