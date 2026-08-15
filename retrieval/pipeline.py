"""What each stage of the pipeline did, for the visualisation.

The diagram is only worth drawing if it reports execution rather than assuming
it. A frontend cannot infer that the reranker was skipped or that a sparse-only
query never embedded anything — those are facts the backend has and must say
out loud, which is what this module carries.
"""

from dataclasses import dataclass
from typing import Literal, Optional

StageName = Literal["embedding", "dense", "sparse", "fusion", "reranker", "generation"]

#: Canonical order, so the diagram reads left to right the way data flows.
STAGE_ORDER: tuple[StageName, ...] = (
    "embedding",
    "dense",
    "sparse",
    "fusion",
    "reranker",
    "generation",
)

StageStatus = Literal["ok", "skipped", "error"]


@dataclass(frozen=True)
class PipelineStage:
    """One stage's contribution to a single request.

    `skipped` means the stage did not run — a sparse-only query embeds nothing,
    and the cross-encoder is not wired into the live path at all. The product
    spec is explicit that these render differently from stages that ran, and
    that the diagram must never animate one that did not.

    `error` is modelled but not yet emitted: a stage that raises aborts the
    request, so the trace never reaches the client. Reporting a partial pipeline
    alongside a failure would need the error paths to carry it, which they do
    not today.

    `candidates_in` / `candidates_out` are None where the notion does not apply
    — embedding consumes a question, not candidates, and generation produces
    text rather than a shortlist.
    """

    name: StageName
    status: StageStatus
    latency_ms: float
    candidates_in: Optional[int] = None
    candidates_out: Optional[int] = None

    @classmethod
    def skipped(cls, name: StageName) -> "PipelineStage":
        """A stage that did not run.

        Latency is zero because nothing was measured, which is why the UI must
        not draw it on the same scale as a stage that took 0.4 ms — one is an
        absence and the other a measurement.
        """
        return cls(name=name, status="skipped", latency_ms=0.0)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 2),
            "candidates_in": self.candidates_in,
            "candidates_out": self.candidates_out,
        }


def fill_skipped(stages: list[PipelineStage]) -> list[PipelineStage]:
    """Return every stage in canonical order, skipping those not reported.

    The diagram draws the whole pipeline every time — a stage that vanishes
    from the picture reads as "this deployment has no reranker" rather than
    "the reranker did not run for this query".
    """
    reported = {stage.name: stage for stage in stages}
    return [reported.get(name) or PipelineStage.skipped(name) for name in STAGE_ORDER]
