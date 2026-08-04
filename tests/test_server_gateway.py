"""Gateway-level tests for CORS policy and unhandled-error disclosure."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, engine  # noqa: E402
from code_navi.server import CORS_ORIGINS, app  # noqa: E402

_BOOM_PATH = "/__boom_for_tests"
_SECRET = "C:/keys/prod.pem"


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def failing_client() -> Generator[TestClient, None, None]:
    """Client with a route that raises, so the global handler is exercised."""

    @app.get(_BOOM_PATH)
    async def _boom() -> None:
        raise RuntimeError(f"connection failed for {_SECRET}")

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc

    app.router.routes = [
        route for route in app.router.routes if getattr(route, "path", None) != _BOOM_PATH
    ]


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


class TestCorsPolicy:
    def test_wildcard_origin_is_not_used(self) -> None:
        # A wildcard cannot be combined with credentials; browsers reject it.
        assert "*" not in CORS_ORIGINS

    def test_allowed_origin_is_echoed(self, client: TestClient) -> None:
        resp = client.get("/health", headers={"Origin": "http://localhost:3000"})

        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert resp.headers["access-control-allow-credentials"] == "true"

    def test_unknown_origin_is_refused(self, client: TestClient) -> None:
        resp = client.get("/health", headers={"Origin": "http://evil.example"})

        assert "access-control-allow-origin" not in resp.headers

    def test_preflight_from_allowed_origin_succeeds(self, client: TestClient) -> None:
        resp = client.options(
            "/api/v1/learning/explain",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"


# ---------------------------------------------------------------------------
# Unhandled errors
# ---------------------------------------------------------------------------


class TestErrorDisclosure:
    def test_internal_error_does_not_leak_exception_text(
        self,
        failing_client: TestClient,
    ) -> None:
        resp = failing_client.get(_BOOM_PATH)

        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "Internal server error."
        assert _SECRET not in resp.text
        assert "RuntimeError" not in resp.text

    def test_internal_error_returns_correlation_id(
        self,
        failing_client: TestClient,
    ) -> None:
        resp = failing_client.get(_BOOM_PATH)

        error_id = resp.json()["error_id"]
        assert isinstance(error_id, str)
        assert len(error_id) == 32

    def test_exception_detail_is_logged_server_side(
        self,
        failing_client: TestClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level("ERROR", logger="code_navi.server"):
            resp = failing_client.get(_BOOM_PATH)

        # The operator keeps what the client is denied, joined by error_id.
        assert resp.json()["error_id"] in caplog.text
        assert _SECRET in caplog.text
