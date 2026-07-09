import csv
from pathlib import Path
from typing import List

from config.logging_config import get_logger
from config.settings import REPORTS_DIR

from .benchmark import BenchmarkResult

logger = get_logger(__name__)


class ReportGenerator:
    """Writes benchmark results to CSV and Markdown."""

    def __init__(self, report_dir: Path | str = REPORTS_DIR) -> None:
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CSV — one row per question
    # ------------------------------------------------------------------

    def save_csv(
        self,
        result: BenchmarkResult,
        filename: str = "evaluation.csv",
    ) -> Path:
        path = self.report_dir / filename
        rows = self._merge_rows(result)
        if not rows:
            return path
        fieldnames = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info("Saved per-question CSV to %s", path)
        return path

    # ------------------------------------------------------------------
    # Markdown summary
    # ------------------------------------------------------------------

    def save_summary(
        self,
        result: BenchmarkResult,
        filename: str = "summary.md",
    ) -> Path:
        path = self.report_dir / filename
        path.write_text(self._render_summary(result), encoding="utf-8")
        logger.info("Saved summary to %s", path)
        return path

    # ------------------------------------------------------------------
    # Experiment sweep — comparison table
    # ------------------------------------------------------------------

    def save_experiment_csv(
        self,
        rows: List[dict],
        filename: str = "experiment_results.csv",
    ) -> Path:
        path = self.report_dir / filename
        if not rows:
            return path
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        logger.info("Saved experiment CSV to %s", path)
        return path

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _merge_rows(self, result: BenchmarkResult) -> List[dict]:
        """One row per question — merged retrieval + generation columns."""
        gen_by_id = {g.question_id: g for g in result.generation_samples}
        rows = []
        for r in result.retrieval_samples:
            g = gen_by_id.get(r.question_id)
            row = {
                "question_id": r.question_id,
                "question": r.question,
                "retrieved_ids": "|".join(r.retrieved_ids),
                "expected_ids": "|".join(r.expected_ids),
                "precision": round(r.precision, 4),
                "recall": round(r.recall, 4),
                "hit": int(r.hit),
                "reciprocal_rank": round(r.reciprocal_rank, 4),
                "retrieval_ms": round(r.latency_ms, 1),
            }
            if g is not None:
                row.update(
                    {
                        "generated_answer": g.generated_answer,
                        "expected_answer": g.expected_answer,
                        "semantic_similarity": round(g.semantic_similarity, 4),
                        "faithful": (
                            str(g.faithful) if g.faithful is not None else "N/A"
                        ),
                        "answer_words": g.answer_words,
                        "generation_ms": round(g.latency_ms, 1),
                    }
                )
            rows.append(row)
        return rows

    def _render_summary(self, result: BenchmarkResult) -> str:
        r = result.retrieval
        g = result.generation
        faith = (
            f"{g.faithfulness_rate:.4f}"
            if g.faithfulness_rate is not None
            else "N/A (faithfulness evaluator not configured)"
        )
        lines = [
            "# Evaluation Summary",
            "",
            f"**Timestamp:** {result.timestamp}",
            f"**Questions evaluated:** {len(result.retrieval_samples)}",
            "",
            "## Retrieval Metrics",
            "",
            f"| Metric | Score |",
            f"|--------|-------|",
            f"| Precision@{r.k} | {r.precision_at_k:.4f} |",
            f"| Recall@{r.k} | {r.recall_at_k:.4f} |",
            f"| Hit Rate | {r.hit_rate:.4f} |",
            f"| MRR | {r.mrr:.4f} |",
            f"| Avg Retrieval Latency | {r.avg_latency_ms:.1f} ms |",
            "",
            "## Generation Metrics",
            "",
            f"| Metric | Score |",
            f"|--------|-------|",
            f"| Semantic Similarity | {g.avg_semantic_similarity:.4f} |",
            f"| Faithfulness Rate | {faith} |",
            f"| Avg Answer Words | {g.avg_answer_words:.1f} |",
            f"| Avg Generation Latency | {g.avg_latency_ms:.1f} ms |",
            "",
            "## Configuration",
            "",
        ]
        for k, v in result.config.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")
        return "\n".join(lines)
