from dataclasses import dataclass, field
from typing import List

from retrieval.ranking import RetrievalResult


@dataclass
class Prompt:
    """Structured prompt that separates system instructions from user content.

    Keeping these two strings distinct lets every LLM client (Groq, OpenAI,
    Anthropic) assemble its own messages array without touching PromptBuilder.
    """

    system: str
    user: str


@dataclass
class GenerationResponse:
    """Carries everything a caller or monitoring system might need.

    sources   — the retrieved chunks that were included in the prompt,
                kept for citation rendering and downstream evaluation
    latency_ms — wall-clock time of the LLM call; CloudWatch / dashboards
                 capture this directly from the log or response object
    """

    answer: str
    sources: List[RetrievalResult]
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
