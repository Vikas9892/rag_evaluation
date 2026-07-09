from typing import List

from config.settings import MAX_CONTEXT_CHUNKS
from retrieval.ranking import RetrievalResult

from .models import Prompt

SYSTEM_PROMPT = """\
You are a precise and helpful assistant.

Rules:
1. Answer the question using ONLY the information provided in the context below.
2. If the context does not contain enough information to answer, respond with exactly: "I don't know."
3. Never add information from outside the provided context.
4. Be concise and direct.\
"""


class PromptBuilder:
    """Assembles a Prompt from a question and a list of RetrievalResults.

    Knows nothing about the LLM or the API — its only output is a Prompt
    dataclass that any generator can consume.
    """

    def __init__(self, max_context_chunks: int = MAX_CONTEXT_CHUNKS) -> None:
        self.max_context_chunks = max_context_chunks

    def build(self, question: str, results: List[RetrievalResult]) -> Prompt:
        context = self._format_context(results[: self.max_context_chunks])
        user = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
        return Prompt(system=SYSTEM_PROMPT, user=user)

    # ------------------------------------------------------------------

    def _format_context(self, results: List[RetrievalResult]) -> str:
        if not results:
            return "(no context provided)"
        parts: List[str] = []
        for i, r in enumerate(results, 1):
            parts.append(f"[Source {i}] ({r.chunk.document_id})\n{r.chunk.text}")
        return "\n\n---\n\n".join(parts)
