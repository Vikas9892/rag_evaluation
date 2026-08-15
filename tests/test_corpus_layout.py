"""Tests for corpus namespacing.

The id reaches the filesystem, so most of these are about refusing ids rather
than resolving them.
"""

import pytest

from config.settings import FAISS_INDEX_FILE, INDEX_DIR, METADATA_FILE
from corpora import (
    DEFAULT_CORPUS_ID,
    InvalidCorpusIdError,
    corpus_layout,
    is_valid_corpus_id,
    list_corpus_ids,
)
from corpora.layout import CORPORA_DIR


class TestDefaultCorpus:
    def test_keeps_the_paths_the_offline_pipeline_already_writes(self):
        # Moving these would invalidate the recorded baseline, break CI's index
        # build and make every previous benchmark number unreproducible.
        layout = corpus_layout(DEFAULT_CORPUS_ID)
        assert layout.metadata_path == METADATA_FILE
        assert layout.faiss_path == FAISS_INDEX_FILE
        assert layout.root == INDEX_DIR

    def test_is_the_default_when_none_is_named(self):
        assert corpus_layout().corpus_id == DEFAULT_CORPUS_ID

    def test_knows_it_is_the_default(self):
        assert corpus_layout(DEFAULT_CORPUS_ID).is_default
        assert not corpus_layout("uploads").is_default


class TestOtherCorpora:
    def test_live_under_their_own_directory(self):
        layout = corpus_layout("my-notes")
        assert layout.root == CORPORA_DIR / "my-notes"
        assert layout.faiss_path.parent == layout.root

    def test_two_corpora_share_no_files(self):
        # The whole point: an upload cannot land in the evaluation index.
        a, b = corpus_layout("alpha"), corpus_layout("beta")
        assert a.faiss_path != b.faiss_path
        assert a.metadata_path != b.metadata_path
        assert corpus_layout(DEFAULT_CORPUS_ID).faiss_path not in (a.faiss_path, b.faiss_path)


class TestIdValidation:
    @pytest.mark.parametrize(
        "corpus_id", ["evaluation", "a", "my-notes", "notes_2", "0abc", "x" * 64]
    )
    def test_accepts_filesystem_safe_ids(self, corpus_id):
        assert is_valid_corpus_id(corpus_id)
        assert corpus_layout(corpus_id).corpus_id == corpus_id

    @pytest.mark.parametrize(
        "corpus_id",
        [
            "../evaluation",
            "../../etc/passwd",
            "a/b",
            "a\\b",
            "..",
            ".",
            "",
            "UPPER",
            "has space",
            "has.dot",
            "-leading-dash",
            "_leading_underscore",
            "x" * 65,
            "nul\x00byte",
        ],
    )
    def test_refuses_anything_that_could_escape_a_directory(self, corpus_id):
        assert not is_valid_corpus_id(corpus_id)
        with pytest.raises(InvalidCorpusIdError):
            corpus_layout(corpus_id)

    def test_refuses_rather_than_sanitises(self):
        # Rewriting a hostile id into a safe one hides the attempt; refusing
        # surfaces it in the logs and to the caller.
        with pytest.raises(InvalidCorpusIdError) as exc:
            corpus_layout("../evaluation")
        assert "../evaluation" in str(exc.value)


class TestExistence:
    def test_a_corpus_with_no_files_does_not_exist(self, tmp_path, monkeypatch):
        monkeypatch.setattr("corpora.layout.CORPORA_DIR", tmp_path / "corpora")
        assert not corpus_layout("never-indexed").exists

    def test_half_an_index_does_not_count_as_existing(self, tmp_path, monkeypatch):
        # Metadata without vectors fails at search time rather than load time,
        # which is a much worse place to discover it.
        monkeypatch.setattr("corpora.layout.CORPORA_DIR", tmp_path / "corpora")
        layout = corpus_layout("half-built")
        layout.root.mkdir(parents=True)
        layout.metadata_path.write_text("[]", encoding="utf-8")

        assert not layout.exists

    def test_listing_includes_the_evaluation_corpus_first(self):
        ids = list_corpus_ids()
        if ids:
            assert ids[0] == DEFAULT_CORPUS_ID

    def test_listing_skips_directories_without_an_index(self, tmp_path, monkeypatch):
        monkeypatch.setattr("corpora.layout.CORPORA_DIR", tmp_path / "corpora")
        (tmp_path / "corpora" / "empty").mkdir(parents=True)

        assert "empty" not in list_corpus_ids()
