import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

# Must be set before app.core.config.Settings is ever instantiated (get_settings() is
# lru_cache'd and app.main builds a module-level `app = create_app()` on import).
# httpx's test client enforces cookie Secure semantics like a real browser — over the
# plain-http ASGI transport tests use, a Secure-flagged cookie is silently withheld on
# every automatic request. The app's real default (cookie_secure=True) is correct and
# unchanged; this override only ever applies inside the test process.
os.environ.setdefault("COOKIE_SECURE", "false")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.session import dispose_engine  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(autouse=True)
async def _reset_db_engine() -> AsyncGenerator[None, None]:
    # app.db.session caches the AsyncEngine/session factory at module scope, bound to
    # whatever event loop was running when it was first created. pytest-asyncio gives
    # each test function its own event loop by default, so a second test reusing the
    # first test's cached engine fails with "Future attached to a different loop".
    # Disposing after every test forces the next one to build a fresh engine on its
    # own loop.
    yield
    await dispose_engine()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def unique_email() -> str:
    # example.com (RFC 2606) validates cleanly with email-validator; reserved TLDs
    # like .test are flagged as "special-use" and rejected even with syntax-only checks.
    return f"test-{uuid.uuid4().hex[:12]}@example.com"


async def signup(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "correcthorse123",
    full_name: str = "Test User",
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={"email": email or unique_email(), "password": password, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}
