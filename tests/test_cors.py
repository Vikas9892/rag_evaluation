"""CORS configuration tests.

The frontend calls this API directly from the browser (ADR 008), so the origin
allowlist is the only thing between a public endpoint that spends Groq budget
and every page on the internet.
"""
import pytest
from fastapi.testclient import TestClient

from api.app import create_app, resolve_allowed_origins

ALLOWED = "http://localhost:3000"
DENIED = "https://evil.example.com"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("ALLOWED_ORIGINS", ALLOWED)
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# resolve_allowed_origins
# ---------------------------------------------------------------------------


class TestResolveAllowedOrigins:
    def test_defaults_to_local_dev_origin(self):
        assert resolve_allowed_origins("") == ["http://localhost:3000"]

    def test_unset_falls_back_to_default(self, monkeypatch):
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        assert resolve_allowed_origins() == ["http://localhost:3000"]

    def test_splits_on_commas(self):
        assert resolve_allowed_origins("http://a.test,http://b.test") == [
            "http://a.test",
            "http://b.test",
        ]

    def test_strips_surrounding_whitespace(self):
        assert resolve_allowed_origins(" http://a.test , http://b.test ") == [
            "http://a.test",
            "http://b.test",
        ]

    def test_drops_blank_entries(self):
        """A trailing comma must not smuggle an empty origin into the allowlist."""
        assert resolve_allowed_origins("http://a.test,,") == ["http://a.test"]

    def test_wildcard_is_permitted_but_warned(self, caplog):
        with caplog.at_level("WARNING"):
            assert resolve_allowed_origins("*") == ["*"]
        assert "open to every origin" in caplog.text

    def test_explicit_allowlist_logs_no_warning(self, caplog):
        with caplog.at_level("WARNING"):
            resolve_allowed_origins("http://a.test")
        assert "open to every origin" not in caplog.text


# ---------------------------------------------------------------------------
# Actual browser behaviour
# ---------------------------------------------------------------------------


class TestSimpleRequests:
    def test_allowed_origin_gets_the_header_back(self, client):
        r = client.get("/health", headers={"Origin": ALLOWED})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == ALLOWED

    def test_disallowed_origin_gets_no_header(self, client):
        """The request still succeeds; the browser is what blocks the read."""
        r = client.get("/health", headers={"Origin": DENIED})
        assert "access-control-allow-origin" not in r.headers

    def test_no_origin_header_is_unaffected(self, client):
        """curl and server-to-server callers send no Origin and must still work."""
        assert client.get("/health").status_code == 200


class TestPreflight:
    def _preflight(self, client, origin: str, method: str = "POST"):
        return client.options(
            "/query",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "content-type",
            },
        )

    def test_allowed_origin_preflight_succeeds(self, client):
        r = self._preflight(client, ALLOWED)
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == ALLOWED

    def test_content_type_header_is_allowed(self, client):
        r = self._preflight(client, ALLOWED)
        assert "content-type" in r.headers["access-control-allow-headers"].lower()

    def test_post_is_allowed(self, client):
        r = self._preflight(client, ALLOWED)
        assert "POST" in r.headers["access-control-allow-methods"]

    def test_delete_is_not_allowed(self, client):
        """Only the verbs the client actually issues are permitted."""
        r = self._preflight(client, ALLOWED, method="DELETE")
        assert "DELETE" not in r.headers.get("access-control-allow-methods", "")

    def test_disallowed_origin_preflight_is_rejected(self, client):
        r = self._preflight(client, DENIED)
        assert "access-control-allow-origin" not in r.headers


class TestCredentials:
    def test_credentials_are_not_allowed(self, client):
        """No cookies or Authorization are used, so credentials stay off."""
        r = client.get("/health", headers={"Origin": ALLOWED})
        assert "access-control-allow-credentials" not in r.headers
