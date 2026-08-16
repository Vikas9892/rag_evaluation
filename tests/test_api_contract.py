"""Guards constants the frontend duplicates from the API schema.

The browser validates `top_k` before sending it so a mistyped URL becomes a
clamped value rather than a 422. That means the bound exists twice, in two
languages, and nothing in either toolchain would notice if one moved. These
tests read the TypeScript source and fail when it stops agreeing with Pydantic.
"""

import re
from typing import get_args

import pytest

from api.schemas import QueryRequest, SourceInfo
from chunking.chunk import Chunk
from config.settings import BASE_DIR
from corpora.layout import DEFAULT_CORPUS_ID, _VALID_CORPUS_ID
from retrieval.ranking import RetrievalResult, RetrievalTrace, StageScore
from services.rag_service import source_payload

QUERY_PARAMS_TS = BASE_DIR / "frontend" / "lib" / "query-params.ts"


def _constant(name: str) -> int:
    """Read `export const NAME = <int>;` out of the TypeScript module."""
    source = QUERY_PARAMS_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\d+);", source)
    assert match, f"{name} is not exported from {QUERY_PARAMS_TS.name}"
    return int(match.group(1))


def _ts_string_array(name: str) -> list[str]:
    """Read `export const NAME = ["a", "b"] as const;` out of the TypeScript."""
    source = QUERY_PARAMS_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = \[(.*?)\] as const;", source, re.S)
    assert match, f"{name} is not exported from {QUERY_PARAMS_TS.name}"
    return re.findall(r'"([^"]+)"', match.group(1))


def _field_bound(kind: str) -> int:
    """Pull ge/le off the Pydantic field's metadata."""
    for constraint in QueryRequest.model_fields["top_k"].metadata:
        if hasattr(constraint, kind):
            return getattr(constraint, kind)
    pytest.fail(f"QueryRequest.top_k has no {kind} constraint")


class TestTopKBounds:
    def test_frontend_file_exists(self):
        # A rename would otherwise make every assertion below vacuous.
        assert QUERY_PARAMS_TS.is_file(), f"missing {QUERY_PARAMS_TS}"

    def test_minimum_matches(self):
        assert _constant("TOP_K_MIN") == _field_bound("ge")

    def test_maximum_matches(self):
        assert _constant("TOP_K_MAX") == _field_bound("le")

    def test_default_matches(self):
        assert _constant("TOP_K_DEFAULT") == QueryRequest.model_fields["top_k"].default

    def test_default_is_within_bounds(self):
        # Cheap, but it is the one combination that would let a valid-looking
        # default produce a request the API rejects.
        assert _field_bound("ge") <= _constant("TOP_K_DEFAULT") <= _field_bound("le")


class TestSourcePayloadMatchesSourceInfo:
    """The streaming and non-streaming paths must describe a chunk identically.

    POST /query builds `SourceInfo(**source_payload(r))`, while /stream puts
    `source_payload(r)` straight on the wire. The frontend types the stream's
    sources as the generated SourceInfo on the strength of that. If the two ever
    diverge, the browser would be reading one shape and typed for another —
    silently, because SSE payloads are not in the OpenAPI schema.
    """

    @staticmethod
    def _result() -> RetrievalResult:
        return RetrievalResult(
            chunk=Chunk(
                chunk_id="doc_chunk_0",
                document_id="doc",
                text="Durability means committed data survives a crash.",
                start_char=0,
                end_char=48,
                metadata={"heading": "ACID"},
            ),
            score=0.42,
            rank=1,
            trace=RetrievalTrace(
                dense=StageScore(score=0.9, rank=1),
                fused=StageScore(score=0.42, rank=1),
            ),
        )

    def test_payload_keys_are_exactly_source_info_fields(self):
        assert set(source_payload(self._result())) == set(SourceInfo.model_fields)

    def test_payload_validates_as_source_info(self):
        model = SourceInfo(**source_payload(self._result()))
        assert model.chunk_id == "doc_chunk_0"
        assert model.scores.dense is not None
        assert model.scores.sparse is None

    def test_a_missing_stage_survives_validation_as_null(self):
        # Pydantic must not coerce an absent stage into a zero-valued object;
        # "did not rank this chunk" and "scored zero" have to stay distinct.
        model = SourceInfo(**source_payload(self._result()))
        assert model.scores.reranker is None


class TestRetrieverModes:
    """The browser validates `retriever` before sending it, so the list exists twice.

    An unknown strategy is a 422, and the frontend falls back to the default
    rather than letting a mistyped URL surface as an error banner. That is only
    correct while its list matches the one the API accepts.
    """

    @staticmethod
    def _accepted() -> set:
        annotation = QueryRequest.model_fields["retriever"].annotation
        return set(get_args(annotation))

    def test_frontend_lists_exactly_what_the_api_accepts(self):
        assert set(_ts_string_array("RETRIEVERS")) == self._accepted()

    def test_frontend_default_is_accepted(self):
        source = QUERY_PARAMS_TS.read_text(encoding="utf-8")
        match = re.search(r'RETRIEVER_DEFAULT: RetrieverMode = "([^"]+)"', source)
        assert match, "RETRIEVER_DEFAULT is not exported"
        assert match.group(1) in self._accepted()

    def test_defaults_agree_across_the_boundary(self):
        source = QUERY_PARAMS_TS.read_text(encoding="utf-8")
        frontend_default = re.search(
            r'RETRIEVER_DEFAULT: RetrieverMode = "([^"]+)"', source
        ).group(1)
        assert frontend_default == QueryRequest.model_fields["retriever"].default


class TestCorpusId:
    """The corpus id pattern and default are duplicated in the browser.

    The frontend refuses an id the API would reject so a hand-edited URL is
    ignored rather than turned into a 422 banner, and it falls back to the same
    default the API uses so a link with no corpus means one thing, not two.
    """

    @staticmethod
    def _frontend_pattern() -> str:
        source = QUERY_PARAMS_TS.read_text(encoding="utf-8")
        match = re.search(r"const VALID_CORPUS_ID = /(.+?)/;", source)
        assert match, "VALID_CORPUS_ID is not declared in query-params.ts"
        return match.group(1)

    @staticmethod
    def _frontend_default() -> str:
        source = QUERY_PARAMS_TS.read_text(encoding="utf-8")
        match = re.search(r'export const CORPUS_DEFAULT = "([^"]+)";', source)
        assert match, "CORPUS_DEFAULT is not exported from query-params.ts"
        return match.group(1)

    def test_pattern_matches_the_one_the_api_enforces(self):
        assert self._frontend_pattern() == _VALID_CORPUS_ID.pattern

    def test_default_matches_the_api(self):
        assert self._frontend_default() == DEFAULT_CORPUS_ID

    @pytest.mark.parametrize(
        "corpus_id",
        ["evaluation", "workspace", "k8s-notes", "a", "a_b-9"],
    )
    def test_both_sides_accept_the_same_valid_ids(self, corpus_id):
        assert re.match(self._frontend_pattern(), corpus_id)
        assert _VALID_CORPUS_ID.match(corpus_id)

    @pytest.mark.parametrize(
        "corpus_id",
        ["../../etc", "Evaluation", "-leading", "_leading", "has space", "", "a" * 65],
    )
    def test_both_sides_refuse_the_same_bad_ids(self, corpus_id):
        # Path traversal is the one that matters: the id becomes a directory
        # name, so an id that escapes the index root is the bug this prevents.
        assert not re.match(self._frontend_pattern(), corpus_id)
        assert not _VALID_CORPUS_ID.match(corpus_id)
