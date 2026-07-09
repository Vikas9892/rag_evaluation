"""Run the full evaluation benchmark and save reports to reports/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os

from config.logging_config import get_logger
from config.settings import TOP_K
from embeddings.embedder import Embedder
from generation.generator import GroqGenerator
from generation.prompt_builder import PromptBuilder
from retrieval.retriever import Retriever

from evaluation.benchmark import BenchmarkRunner
from evaluation.dataset import DatasetLoader
from evaluation.report import ReportGenerator

logger = get_logger(__name__)

DIVIDER = "-" * 52


def _build_generator():
    """Return a GroqGenerator if the API key is present, else None."""
    if os.environ.get("GROQ_API_KEY"):
        try:
            return GroqGenerator()
        except Exception as exc:
            logger.warning("Could not initialise GroqGenerator: %s", exc)
    return None


def main() -> None:
    print("Loading pipeline...", end=" ", flush=True)
    dataset = DatasetLoader.load()
    retriever = Retriever.from_disk()
    embedder = Embedder()
    builder = PromptBuilder()
    generator = _build_generator()
    reporter = ReportGenerator()
    print("ready.\n")

    if generator is None:
        print(
            "Note: GROQ_API_KEY not set. Running retrieval + semantic-similarity "
            "evaluation only. Set GROQ_API_KEY to enable generation + faithfulness.\n"
        )

    # Use a pass-through mock when no real generator is available so the
    # BenchmarkRunner can still compute semantic similarity.
    from generation.generator import BaseGenerator
    from generation.models import GenerationResponse

    class _PassthroughGenerator(BaseGenerator):
        """Returns the expected answer unchanged — no API call."""
        def generate(self, prompt, sources):
            question_line = next(
                (l for l in prompt.user.splitlines() if "Question:" in l), ""
            )
            return GenerationResponse(
                answer="(generation skipped — set GROQ_API_KEY to enable)",
                sources=sources,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=0.0,
            )

    active_generator = generator or _PassthroughGenerator()
    faithfulness_generator = generator  # None unless Groq is available

    print(f"Running Benchmark...")
    print(f"Questions: {len(dataset)}\n")

    runner = BenchmarkRunner(
        retriever=retriever,
        generator=active_generator,
        embedder=embedder,
        builder=builder,
        dataset=dataset,
        top_k=TOP_K,
        faithfulness_generator=faithfulness_generator,
    )
    result = runner.run()

    # --- Print summary ---
    r = result.retrieval
    g = result.generation
    print(f"Precision@{r.k}: {r.precision_at_k:.4f}")
    print(f"Recall@{r.k}:    {r.recall_at_k:.4f}")
    print(f"Hit Rate:     {r.hit_rate:.4f}")
    print(f"MRR:          {r.mrr:.4f}")
    print()
    print(f"Semantic Similarity: {g.avg_semantic_similarity:.4f}")
    if g.faithfulness_rate is not None:
        print(f"Faithfulness:        {g.faithfulness_rate:.4f}")
    else:
        print("Faithfulness:        N/A")
    print()
    print(f"Avg Retrieval Latency:   {r.avg_latency_ms:.1f} ms")
    if generator is not None:
        print(f"Avg Generation Latency: {g.avg_latency_ms:.1f} ms")

    # --- Save reports ---
    csv_path = reporter.save_csv(result)
    summary_path = reporter.save_summary(result)
    print(f"\n{DIVIDER}")
    print(f"Results saved to {csv_path}")
    print(f"Summary saved to {summary_path}")


if __name__ == "__main__":
    main()
