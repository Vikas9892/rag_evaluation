import os
import time
from abc import ABC, abstractmethod
from typing import Generator, List

from config.logging_config import get_logger
from config.settings import (
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
)
from retrieval.ranking import RetrievalResult

from .models import GenerationResponse, Prompt

logger = get_logger(__name__)

# Retry on these transient error categories; fail-fast on auth / bad-request.
_RETRYABLE = ("RateLimitError", "APIConnectionError", "APITimeoutError")


class BaseGenerator(ABC):
    """Provider-agnostic interface for all LLM backends.

    Any class that implements generate() can slot into the pipeline without
    touching the retriever, prompt builder, or evaluation code.
    """

    @abstractmethod
    def generate(
        self, prompt: Prompt, sources: List[RetrievalResult]
    ) -> GenerationResponse:
        """Call the LLM and return a fully-populated GenerationResponse."""

    def stream(
        self, prompt: Prompt, sources: List[RetrievalResult]
    ) -> Generator[str, None, None]:
        """Yield answer tokens one by one as they arrive from the LLM.

        Default implementation raises NotImplementedError — override in
        concrete subclasses that support server-sent streaming (e.g. Groq).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support streaming"
        )
        yield  # make this a generator function even without overriding


class GroqGenerator(BaseGenerator):
    """Groq-backed generator with exponential-backoff retries.

    Retries: RateLimitError, APIConnectionError, APITimeoutError.
    Fails immediately: AuthenticationError, BadRequestError, and any
    other 4xx that signals a permanent client-side problem.

    Token counts default to 0 when the API omits usage data (some streaming
    configurations), so callers never receive None.
    """

    def __init__(
        self,
        model: str = LLM_MODEL,
        api_key: str | None = None,
        temperature: float = LLM_TEMPERATURE,
        max_tokens: int = LLM_MAX_TOKENS,
        timeout: float = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        from groq import Groq  # deferred so missing package only fails at runtime

        resolved_key = api_key or os.environ.get("GROQ_API_KEY")
        if not resolved_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. "
                "Export it as an environment variable before running."
            )

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = Groq(api_key=resolved_key)
        logger.info("GroqGenerator ready (model=%s)", model)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate(
        self, prompt: Prompt, sources: List[RetrievalResult]
    ) -> GenerationResponse:
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]

        t0 = time.perf_counter()
        completion = self._call_with_retry(messages)
        latency_ms = (time.perf_counter() - t0) * 1000

        answer = completion.choices[0].message.content or ""
        usage = completion.usage
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0

        logger.info(
            "Generated answer | latency=%.0f ms | tokens=%d+%d | model=%s",
            latency_ms,
            prompt_tokens,
            completion_tokens,
            self.model,
        )

        return GenerationResponse(
            answer=answer,
            sources=sources,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def stream(
        self, prompt: Prompt, sources: List[RetrievalResult]
    ) -> Generator[str, None, None]:
        """Yield answer tokens as they arrive from the Groq streaming API."""
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    def _call_with_retry(self, messages: list):
        import groq as _groq

        delay = 1.0
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                return self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=self.timeout,
                )
            except (
                _groq.RateLimitError,
                _groq.APIConnectionError,
                _groq.APITimeoutError,
            ) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    logger.warning(
                        "%s (attempt %d/%d) — retrying in %.1fs",
                        type(exc).__name__,
                        attempt,
                        self.max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
            except Exception:
                # AuthenticationError, BadRequestError, etc. — fail immediately
                raise

        raise last_exc  # type: ignore[misc]
