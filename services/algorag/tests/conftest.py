"""
Shared pytest configuration for the AlgoRAG test suite.

Marker conventions used in this package:

* ``infrastructure`` -- the test needs a live Qdrant server (localhost:6333).
  Deselect with ``-m "not infrastructure"``; this is the default in the
  backend config and the planned unified config.
* ``integration`` -- end-to-end test against Qdrant (kept alongside
  ``infrastructure`` on the live-server classes for backwards compatibility).
* ``performance`` -- latency/throughput benchmark, registered below.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "performance: AlgoRAG latency/throughput benchmarks (usually also infrastructure)",
    )


@asynccontextmanager
async def _offline_lifespan(app):  # noqa: ARG001 - signature required by Starlette
    yield


@pytest.fixture(autouse=True)
def _offline_app_lifespan(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Keep the FastAPI startup hook from connecting to a real Qdrant.

    ``services.algorag.main.lifespan`` builds a real ``QdrantClientWrapper`` and
    calls ``ensure_collection()`` against QDRANT_HOST:QDRANT_PORT. Every
    ``with TestClient(app)`` block in the endpoint tests ran that hook. With no
    server running, each test waited for the connection attempts to fail
    (about 7s on Windows). With a developer's local Qdrant running, the tests
    would have created the real ``trading_setups`` collection. Endpoint tests
    inject their own mock through ``get_qdrant()`` and never use the startup
    connection, so the hook is replaced with a no-op here. Tests marked
    ``infrastructure`` keep the real lifespan.
    """
    if request.node.get_closest_marker("infrastructure") is not None:
        return
    import services.algorag.main as svc_main

    monkeypatch.setattr(svc_main.app.router, "lifespan_context", _offline_lifespan)
