"""Tests for chunking configuration and the settings taxonomy.

Chunking is an indexing-time decision. These pin both halves of that: the
configuration refuses combinations that would produce a useless index, and the
API says which settings a request can change and which need a rebuild.
"""

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from chunking.config import DEFAULT_CHUNKING, ChunkingConfig, InvalidChunkingConfig
from chunking.splitter import DocumentSplitter
from ingestion.document import Document


class TestChunkingConfig:
    def test_defaults_match_the_shipped_pipeline(self):
        # Changing these would silently re-chunk the corpus and move every
        # published metric.
        assert DEFAULT_CHUNKING.chunk_size == 250
        assert DEFAULT_CHUNKING.chunk_overlap == 50

    def test_refuses_an_overlap_at_or_above_the_chunk_size(self):
        # The splitter would make no forward progress, or duplicate nearly the
        # whole document across neighbouring chunks.
        with pytest.raises(InvalidChunkingConfig, match="smaller than chunk_size"):
            ChunkingConfig(chunk_size=200, chunk_overlap=200)

    def test_refuses_a_negative_overlap(self):
        with pytest.raises(InvalidChunkingConfig):
            ChunkingConfig(chunk_overlap=-1)

    def test_refuses_a_chunk_too_small_to_hold_a_sentence(self):
        with pytest.raises(InvalidChunkingConfig, match="at least 50"):
            ChunkingConfig(chunk_size=10)

    def test_clamps_the_minimum_below_half_the_chunk_size(self):
        # A threshold at or above chunk_size classifies every chunk as short and
        # cascades the document into one blob.
        config = ChunkingConfig(chunk_size=200, chunk_overlap=20, min_chunk_chars=500)
        assert config.effective_min_chunk_chars == 100

    def test_reports_the_minimum_it_will_actually_apply(self):
        # The caller should see what its setting really does, not what it asked.
        config = ChunkingConfig(chunk_size=100, chunk_overlap=10, min_chunk_chars=90)
        assert config.as_dict()["min_chunk_chars"] == 50


class TestSplitterFromConfig:
    def test_builds_a_splitter_that_honours_the_config(self):
        config = ChunkingConfig(chunk_size=120, chunk_overlap=20)
        splitter = DocumentSplitter.from_config(config)

        assert splitter.chunk_size == 120
        assert splitter.chunk_overlap == 20

    def test_the_resulting_chunks_respect_the_size(self):
        text = "Sentence about networking protocols. " * 40
        splitter = DocumentSplitter.from_config(
            ChunkingConfig(chunk_size=150, chunk_overlap=20, min_chunk_chars=0)
        )
        chunks = splitter.split(Document(id="d", source="d.md", text=text))

        assert chunks
        # Recursive splitting can overshoot slightly on an unsplittable run;
        # the bound that matters is that it is not producing one giant chunk.
        assert max(len(c.text) for c in chunks) < 400

    def test_a_smaller_chunk_size_produces_more_chunks(self):
        text = "Sentence about networking protocols. " * 40
        doc = Document(id="d", source="d.md", text=text)

        few = DocumentSplitter.from_config(ChunkingConfig(chunk_size=400, chunk_overlap=20))
        many = DocumentSplitter.from_config(ChunkingConfig(chunk_size=120, chunk_overlap=20))

        assert len(many.split(doc)) > len(few.split(doc))


class TestSettingsEndpoint:
    @pytest.fixture
    def client(self):
        with TestClient(create_app()) as c:
            yield c

    def test_groups_settings_by_area(self, client):
        groups = client.get("/settings").json()["groups"]
        assert set(groups) == {"retrieval", "generation", "indexing"}

    def test_query_time_settings_need_no_reindex(self, client):
        groups = client.get("/settings").json()["groups"]
        assert all(not s["requires_reindex"] for s in groups["retrieval"])
        assert all(s["scope"] == "query" for s in groups["retrieval"])

    def test_every_indexing_setting_requires_a_reindex(self, client):
        # This is the distinction the UI must not blur: a chunk-size slider
        # beside top-K would promise an instant effect it cannot have.
        groups = client.get("/settings").json()["groups"]
        assert all(s["requires_reindex"] for s in groups["indexing"])

    def test_the_embedding_model_is_not_editable_per_request(self, client):
        groups = client.get("/settings").json()["groups"]
        model = next(s for s in groups["indexing"] if s["key"] == "embedding_model")

        assert model["editable_per_request"] is False
        assert "meaningless" in model["note"]

    def test_chunk_size_explains_that_it_applies_to_new_documents_only(self, client):
        groups = client.get("/settings").json()["groups"]
        chunk_size = next(s for s in groups["indexing"] if s["key"] == "chunk_size")

        assert chunk_size["editable_per_request"] is True
        assert "afterwards" in chunk_size["note"]

    def test_temperature_explains_why_it_is_zero(self, client):
        groups = client.get("/settings").json()["groups"]
        temperature = next(s for s in groups["generation"] if s["key"] == "llm_temperature")
        assert "measure nothing" in temperature["note"]
