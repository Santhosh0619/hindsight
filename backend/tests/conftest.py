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
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.session import dispose_engine, get_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _setup_checkpointer_schema() -> None:
    # The real app creates the LangGraph checkpointer's tables (checkpoints,
    # checkpoint_writes, ...) in main.py's lifespan startup -- but the `client` fixture
    # below builds the ASGI app directly over ASGITransport without triggering lifespan
    # events, so nothing ever runs that setup during a test session. Any test whose
    # request path touches AsyncPostgresSaver (e.g. POST .../brief, now that
    # generate_brief routes through the real checkpointer) needs this schema to already
    # exist, regardless of which test file happens to run first alphabetically -- doing
    # it once here, before any test starts, replaces a fragile dependency on
    # test_checkpointer.py's own setup() call running first.
    import asyncio

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from app.agents.build_graph import checkpointer_conn_string
    from app.core.config import get_settings

    async def _setup() -> None:
        conn_string = checkpointer_conn_string(get_settings())
        async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
            await saver.setup()

    asyncio.run(_setup())


@pytest.fixture(autouse=True)
def _reset_rate_limit_buckets() -> None:
    # login_bucket/brief_bucket/demo_signup_bucket/demo_brief_bucket are module-level
    # singletons shared across the whole pytest process, not per-test state -- almost
    # every test in this suite calls signup()/login() as its own setup step, so without
    # a reset here the shared login_bucket empties partway through a full-suite run and
    # every later test's signup() starts getting a real 429, cascading into unrelated
    # failures across dozens of files that have nothing to do with rate limiting.
    from app.services.rate_limit import (
        brief_bucket,
        demo_brief_bucket,
        demo_signup_bucket,
        login_bucket,
    )

    for bucket in (login_bucket, brief_bucket, demo_brief_bucket, demo_signup_bucket):
        bucket._buckets.clear()


@pytest.fixture(autouse=True)
def _prevent_real_ollama_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    # No test may touch the network (Master-Prompt.md's Phase 15 checkpoint).
    # OllamaLLMProvider is *always* constructed regardless of whether an LLM key is
    # configured (Ollama needs none) -- both build_router() (called for real inside
    # the actual POST .../incidents/{id}/brief route handler, not just LLM-specific
    # unit tests) and llm_test_service.test_all_providers() build a real one. Patching
    # the three LLMProvider protocol methods at the class level (not per-module import
    # site) closes every call path in one place, rather than requiring every test file
    # that happens to exercise one of those routes to remember its own mock.
    from app.services.llm.ollama import OllamaLLMProvider

    async def _fail(self: object, *args: object, **kwargs: object) -> None:
        raise ConnectionError("mocked: nothing listening at ollama_base_url")

    monkeypatch.setattr(OllamaLLMProvider, "complete", _fail)
    monkeypatch.setattr(OllamaLLMProvider, "structured", _fail)
    monkeypatch.setattr(OllamaLLMProvider, "structured_with_usage", _fail)


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


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    # A raw session for tests that exercise a service/worker module directly (queue
    # claim/backoff, ingestion pipeline steps) rather than through the HTTP API.
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


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


class FakeModelProvider:
    """Wraps a pydantic-ai Model (TestModel/FunctionModel) as an LLMProvider, so
    extraction-agent tests exercise the real Agent(model, output_type=...) code path
    without a real network call -- no LLM key is configured for this build session."""

    def __init__(self, model: object) -> None:
        self.model_name = "test"
        self._model = model

    async def complete(self, prompt: str, *, system: str) -> Any:
        from pydantic_ai import Agent

        from app.services.llm.provider import LLMResponse

        agent = Agent(self._model, system_prompt=system)  # type: ignore[arg-type]
        result = await agent.run(prompt)
        return LLMResponse(
            text=str(result.output),
            tokens_in=result.usage.input_tokens,
            tokens_out=result.usage.output_tokens,
            model=self.model_name,
        )

    async def structured(self, prompt: str, *, system: str, result_type: Any) -> Any:
        from pydantic_ai import Agent

        agent = Agent(self._model, output_type=result_type, system_prompt=system)  # type: ignore[arg-type]
        result = await agent.run(prompt)
        return result.output

    async def structured_with_usage(self, prompt: str, *, system: str, result_type: Any) -> Any:
        from pydantic_ai import Agent

        from app.services.llm.provider import LLMResponse

        agent = Agent(self._model, output_type=result_type, system_prompt=system)  # type: ignore[arg-type]
        result = await agent.run(prompt)
        usage = LLMResponse(
            text="",
            tokens_in=result.usage.input_tokens,
            tokens_out=result.usage.output_tokens,
            model=self.model_name,
        )
        return result.output, usage
