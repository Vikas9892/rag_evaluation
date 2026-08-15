"""Guards constants the frontend duplicates from the API schema.

The browser validates `top_k` before sending it so a mistyped URL becomes a
clamped value rather than a 422. That means the bound exists twice, in two
languages, and nothing in either toolchain would notice if one moved. These
tests read the TypeScript source and fail when it stops agreeing with Pydantic.
"""

import re
from pathlib import Path

import pytest

from api.schemas import QueryRequest
from config.settings import BASE_DIR

QUERY_PARAMS_TS = BASE_DIR / "frontend" / "lib" / "query-params.ts"


def _constant(name: str) -> int:
    """Read `export const NAME = <int>;` out of the TypeScript module."""
    source = QUERY_PARAMS_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\d+);", source)
    assert match, f"{name} is not exported from {QUERY_PARAMS_TS.name}"
    return int(match.group(1))


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
