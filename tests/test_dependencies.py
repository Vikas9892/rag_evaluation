"""Tests for the process-scoped singletons in `api.dependencies`.

Two things live here that nothing else covers.

The **service builder** loads a real corpus: a FAISS index, a BM25 store and a
Groq client. It used to be exercised incidentally, because `/settings` asked
for a RAGService it never used; removing that dependency fixed the endpoint and
left this path untested, which is the wrong trade to make silently.

The **shutdown path** closes the document repository. A repository that is
never closed leaves its SQLite connections open until the interpreter collects
them — a ResourceWarning, and on Windows a database file still locked while the
directory holding it is being removed.
"""

import pytest

from api import dependencies
from documents import DocumentRepository


@pytest.fixture(autouse=True)
def clean_singletons():
    """Leave no cached service or repository behind for the next test."""
    dependencies._build_service_for.cache_clear()
    dependencies._build_document_repository.cache_clear()
    yield
    dependencies._build_service_for.cache_clear()
    dependencies._build_document_repository.cache_clear()


class TestServiceBuilder:
    @pytest.fixture(autouse=True)
    def api_key(self, monkeypatch):
        # A key the Groq client accepts at construction. Nothing here calls the
        # API — the builder only needs a client to exist — so a fake value keeps
        # the test running where no real key is configured, which is CI.
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_not_a_real_key")

    def test_builds_a_service_over_the_real_evaluation_corpus(self):
        service = dependencies._build_service()

        assert service.corpus_size() > 0
        assert service.document_count() > 0

    def test_caches_the_service_rather_than_reloading_the_index(self):
        # Loading a corpus costs an index read and a model; a query must not
        # pay it twice.
        assert dependencies._build_service() is dependencies._build_service()

    def test_an_unknown_corpus_is_a_404(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as raised:
            dependencies.get_service_for_corpus("no-such-corpus")

        assert raised.value.status_code == 404

    def test_an_invalid_corpus_id_is_a_422(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as raised:
            dependencies.get_service_for_corpus("../etc")

        assert raised.value.status_code == 422


class TestServiceBuilderWithoutAKey:
    def test_a_missing_groq_key_is_a_503_not_a_crash(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as raised:
            dependencies.get_service()

        assert raised.value.status_code == 503


class TestShutdown:
    def test_closing_the_worker_closes_the_repository(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            dependencies,
            "_build_document_repository",
            _cached_repository(tmp_path / "documents.db"),
        )
        repository = dependencies.get_document_repository()

        dependencies.stop_indexing_worker()

        # Closed, and no longer handed out: the next caller must get a usable
        # repository rather than this one.
        assert repository._closed
        with pytest.raises(RuntimeError):
            _use_from_a_fresh_thread(repository)

    def test_shutdown_is_safe_to_run_twice(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            dependencies,
            "_build_document_repository",
            _cached_repository(tmp_path / "documents.db"),
        )
        dependencies.get_document_repository()

        dependencies.stop_indexing_worker()
        dependencies.stop_indexing_worker()  # must not raise


def _cached_repository(path):
    """A stand-in for the lru_cached builder, over a throwaway database."""
    from functools import lru_cache

    @lru_cache(maxsize=1)
    def build() -> DocumentRepository:
        return DocumentRepository(path)

    return build


def _use_from_a_fresh_thread(repository: DocumentRepository) -> None:
    """Force a new connection, which a closed repository must refuse.

    From the calling thread the thread-local is already cleared by close(), so
    this exercises the same guard without needing a second thread.
    """
    repository.list()
