from contextlib import asynccontextmanager
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


class _FakeConnection:
    def __init__(self, *, raise_on_execute: bool) -> None:
        self._raise_on_execute = raise_on_execute

    async def execute(self, *_args: Any, **_kwargs: Any) -> None:
        if self._raise_on_execute:
            raise ConnectionRefusedError("db unreachable")


class _FakeEngine:
    def __init__(self, *, raise_on_execute: bool) -> None:
        self._raise_on_execute = raise_on_execute

    @asynccontextmanager
    async def connect(self) -> Any:
        yield _FakeConnection(raise_on_execute=self._raise_on_execute)


@pytest.fixture
def app_client_factory(monkeypatch: pytest.MonkeyPatch) -> Any:
    def _make(*, db_reachable: bool) -> AsyncClient:
        monkeypatch.setattr(
            "app.main.get_engine",
            lambda: _FakeEngine(raise_on_execute=not db_reachable),
        )
        app = create_app()
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return _make


async def test_health_reports_ok_when_db_reachable(app_client_factory: Any) -> None:
    async with app_client_factory(db_reachable=True) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db_connected"] is True
    assert "version" in body
    assert "llm_configured" in body


async def test_health_degrades_when_db_unreachable(app_client_factory: Any) -> None:
    async with app_client_factory(db_reachable=False) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db_connected"] is False
