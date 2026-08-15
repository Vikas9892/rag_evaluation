import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Generator, Iterator, List, Optional

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
    # Streaming
    # ------------------------------------------------------------------

    def stream(
        self, question: str, top_k: Optional[int] = None
    ) -> Generator[dict, None, None]:
        """Yield SSE-ready event dicts: sources → tokens → done.

        The 'done' event carries the same request_id and latency breakdown that
        answer() returns. Without it a streamed query is untraceable — the id in
        the logs would have nothing to join against on the client — and the
        latency this platform exists to report would be missing from the path
        the UI actually uses.

        It also carries time-to-first-token, which only the streaming path can
        measure and which is the number a user actually experiences: an answer
        that starts in 200 ms and finishes in 3 s feels faster than one that
        appears whole at 1.5 s.
        """
        request_id = str(uuid.uuid4())
        k = top_k if top_k is not None else self._default_top_k

        try:
            t0 = time.perf_counter()
            results = self._retriever.retrieve(question, top_k=k)
            retrieval_ms = (time.perf_counter() - t0) * 1000

            sources = [
                {
                    "document_id": r.chunk.document_id,
                    "chunk_id": r.chunk.chunk_id,
                    "score": round(r.score, 4),
                }
                for r in results
            ]
            yield {"type": "sources", "data": sources}

            prompt = self._builder.build(question, results)

            generation_start = time.perf_counter()
            first_token_ms = None
            token_count = 0
            for token in self._generator.stream(prompt, results):
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - generation_start) * 1000
                token_count += 1
                yield {"type": "token", "data": token}
            generation_ms = (time.perf_counter() - generation_start) * 1000

            self._metrics.total_queries += 1
            self._metrics.total_retrieval_ms += retrieval_ms
            self._metrics.total_generation_ms += generation_ms
        except Exception:
            # Counted here as well as in answer(); a platform that reports
            # total_queries while ignoring every streamed one is misreporting.
            self._metrics.errors += 1
            raise

        logger.info(
            json.dumps({
                "event": "stream",
                "request_id": request_id,
                "question_len": len(question),
                "chunks_retrieved": len(results),
                "retrieval_ms": round(retrieval_ms, 1),
                "generation_ms": round(generation_ms, 1),
                "first_token_ms": (
                    round(first_token_ms, 1) if first_token_ms is not None else None
                ),
                "total_ms": round(retrieval_ms + generation_ms, 1),
                "tokens": token_count,
            })
        )

        yield {
            "type": "done",
            "data": {
                "request_id": request_id,
                "retrieval_latency_ms": round(retrieval_ms, 1),
                "generation_latency_ms": round(generation_ms, 1),
                "total_latency_ms": round(retrieval_ms + generation_ms, 1),
                # None when the model produced no tokens at all, which is a
                # different situation from "arrived instantly".
                "first_token_latency_ms": (
                    round(first_token_ms, 1) if first_token_ms is not None else None
                ),
            },
        }

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict:
        return self._metrics.as_dict()
