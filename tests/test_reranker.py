"""Tests for CrossEncoderReranker — mocked to avoid model downloads."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from chunking.chunk import Chunk
from retrieval.ranking import RetrievalResult
from retrieval.reranker import BaseReranker, CrossEncoderReranker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(idx: int, score: float = 0.5) -> RetrievalResult:
    chunk = Chunk(
        chunk_id=f"chunk_{idx}",
        document_id="doc",
        text=f"This is passage number {idx}.",
        start_char=idx * 50,
        end_char=idx * 50 + 30,
    )
    return RetrievalResult(chunk=chunk, score=score, rank=idx + 1)


# ---------------------------------------------------------------------------
# BaseReranker interface
# ---------------------------------------------------------------------------

class TestBaseRerankerInterface:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseReranker()

    def test_concrete_subclass_must_implement_rerank(self):
        class Bad(BaseReranker):
            pass

        with pytest.raises(TypeError):
            Bad()


# ---------------------------------------------------------------------------
# CrossEncoderReranker (mocked model)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_cross_encoder(monkeypatch):
    """Patch CrossEncoder so no model is downloaded during tests."""
    mock_model = MagicMock()
    # Simulate scores: passage 2 is most relevant (score=0.9), then 0 (0.7), then 1 (0.3)
    mock_model.predict.return_value = np.array([0.7, 0.3, 0.9])

    with patch("retrieval.reranker.CrossEncoder", return_value=mock_model):
        reranker = CrossEncoderReranker(model_name="mock-model")
        reranker._model = mock_model
        yield reranker


class TestCrossEncoderReranker:
    def test_reranker_is_base_reranker(self, mock_cross_encoder):
        assert isinstance(mock_cross_encoder, BaseReranker)

    def test_reranks_by_score_descending(self, mock_cross_encoder):
        results = [_result(0, 0.5), _result(1, 0.4), _result(2, 0.3)]
        reranked = mock_cross_encoder.rerank("query", results, top_k=3)
        # Mock scores: idx0=0.7, idx1=0.3, idx2=0.9 → order: 2, 0, 1
        assert reranked[0].chunk.chunk_id == "chunk_2"
        assert reranked[1].chunk.chunk_id == "chunk_0"
        assert reranked[2].chunk.chunk_id == "chunk_1"

    def test_top_k_limits_output(self, mock_cross_encoder):
        results = [_result(i) for i in range(3)]
        reranked = mock_cross_encoder.rerank("query", results, top_k=2)
        assert len(reranked) == 2

    def test_ranks_are_reset_after_reranking(self, mock_cross_encoder):
        results = [_result(i) for i in range(3)]
        reranked = mock_cross_encoder.rerank("query", results, top_k=3)
        assert [r.rank for r in reranked] == [1, 2, 3]

    def test_scores_are_floats(self, mock_cross_encoder):
        results = [_result(i) for i in range(3)]
        reranked = mock_cross_encoder.rerank("query", results, top_k=3)
        assert all(isinstance(r.score, float) for r in reranked)

    def test_empty_input_returns_empty(self, mock_cross_encoder):
        assert mock_cross_encoder.rerank("query", [], top_k=5) == []

    def test_model_called_with_correct_pairs(self, mock_cross_encoder):
        results = [_result(0), _result(1)]
        mock_cross_encoder.rerank("what is this?", results, top_k=2)
        call_args = mock_cross_encoder._model.predict.call_args[0][0]
        assert call_args[0] == ("what is this?", results[0].chunk.text)
        assert call_args[1] == ("what is this?", results[1].chunk.text)
