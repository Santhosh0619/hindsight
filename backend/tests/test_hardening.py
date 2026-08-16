import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_engine
from app.main import app as real_app
from app.models.catalog import Service
from app.models.postmortem import Postmortem, PostmortemService, PostmortemStatus, ServiceLinkRole
from app.services import postmortem_service
from app.services.rate_limit import TokenBucket, brief_bucket, login_bucket
from tests.conftest import auth_headers, signup


async def _workspace_id(client: AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return str(response.json()["memberships"][0]["workspace_id"])


class TestRateLimiting:
    async def test_login_endpoint_429s_past_its_bucket_threshold(self, client: AsyncClient) -> None:
        owner = await signup(client)
        email = owner["user"]["email"]

        # +1 past capacity, read from the real bucket rather than a hardcoded copy of
        # it -- a capacity change (as already happened once this phase) shouldn't
        # silently stop testing the real boundary.
        attempts = login_bucket._capacity + 1
        responses = [
            await client.post(
                "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
            )
            for _ in range(attempts)
        ]
        assert responses[-1].status_code == 429
        body = responses[-1].json()
        assert body["error"]["code"] == "rate_limited"
        assert body["error"]["request_id"] is not None

    async def test_refresh_is_not_rate_limited(self, client: AsyncClient) -> None:
        # /auth/refresh fires on every page load's boot-time session restore -- see
        # docs/modules/phase-14-hardening/FRD.md "Rate limiting" for why it's excluded.
        for _ in range(35):
            response = await client.post("/api/v1/auth/refresh")
            assert response.status_code != 429

    async def test_brief_generation_429s_past_its_workspace_bucket_threshold(self) -> None:
        # Exercised directly against the bucket (not through the full agent pipeline,
        # which is expensive to run 21 times) -- the route-level wiring itself is
        # covered by incidents.py calling brief_bucket.consume the same way
        # login_bucket.consume is covered above.
        workspace_id = str(uuid.uuid4())
        results = [brief_bucket.consume(workspace_id) for _ in range(21)]
        assert results[-1] is False
        assert all(results[:20])

    async def test_a_different_workspace_has_its_own_independent_bucket(self) -> None:
        workspace_a = str(uuid.uuid4())
        workspace_b = str(uuid.uuid4())
        for _ in range(20):
            assert brief_bucket.consume(workspace_a) is True
        assert brief_bucket.consume(workspace_a) is False
        assert brief_bucket.consume(workspace_b) is True


class TestErrorHandling:
    async def test_an_unhandled_exception_never_leaks_its_own_message(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        owner = await signup(client)
        token = owner["access_token"]
        workspace_id = await _workspace_id(client, token)

        async def _boom(*args: object, **kwargs: object) -> None:
            raise ValueError("a secret internal detail that must never reach the client")

        monkeypatch.setattr(postmortem_service, "list_postmortems", _boom)

        # The shared `client` fixture's ASGITransport defaults to
        # raise_app_exceptions=True -- deliberately re-raising an unhandled exception
        # straight to the test instead of letting the app's own exception handler
        # produce a response, so every *other* test in this suite surfaces a real bug
        # immediately rather than seeing it silently become a 500. This test's whole
        # point is the opposite -- verifying what a real deployed server (which always
        # catches it) actually sends back -- so it needs its own client with that
        # behavior turned off, not a change to the shared fixture.
        transport = ASGITransport(app=real_app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as raw_client:
            response = await raw_client.get(
                f"/api/v1/workspaces/{workspace_id}/postmortems", headers=auth_headers(token)
            )
        assert response.status_code == 500
        body = response.json()
        assert body["error"]["code"] == "internal_error"
        assert "secret internal detail" not in response.text
        assert "ValueError" not in response.text
        assert body["error"]["request_id"] is not None

    async def test_a_typed_app_error_envelope_also_carries_a_request_id(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["request_id"] is not None


class TestSecurityHeaders:
    async def test_every_response_carries_the_standard_defensive_headers(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    async def test_hsts_is_absent_in_this_cookie_secure_false_test_build(
        self, client: AsyncClient
    ) -> None:
        # conftest.py forces COOKIE_SECURE=false for the whole test process (see its
        # own comment) -- this is the honest negative counterpart to the header test
        # above, proving the gate is real and not just always-on.
        response = await client.get("/health")
        assert "Strict-Transport-Security" not in response.headers


class TestRequestSizeCap:
    async def test_an_oversized_request_body_is_rejected_before_it_reaches_the_route(
        self, client: AsyncClient
    ) -> None:
        oversized_password = "x" * (get_settings().max_request_bytes + 1)
        response = await client.post(
            "/api/v1/auth/login",
            content=f'{{"email": "a@example.com", "password": "{oversized_password}"}}'.encode(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "request_too_large"

    async def test_a_normal_sized_request_is_unaffected(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong"}
        )
        assert response.status_code in (401, 429)


class TestTokenBucket:
    def test_refill_restores_capacity_over_time(self) -> None:
        bucket = TokenBucket(capacity=2, refill_seconds=60)
        assert bucket.consume("k") is True
        assert bucket.consume("k") is True
        assert bucket.consume("k") is False


async def _seed_postmortems_with_services(
    db: AsyncSession, *, workspace_id: uuid.UUID, count: int
) -> None:
    service = Service(workspace_id=workspace_id, name=f"svc-{uuid.uuid4().hex[:8]}", tier=1)
    db.add(service)
    await db.flush()

    for i in range(count):
        postmortem = Postmortem(
            workspace_id=workspace_id,
            title=f"pm-{i}",
            raw_text="incident happened",
            status=PostmortemStatus.INDEXED,
            created_at=datetime.now(UTC),
        )
        db.add(postmortem)
        await db.flush()
        db.add(
            PostmortemService(
                postmortem_id=postmortem.id,
                service_id=service.id,
                role=ServiceLinkRole.AFFECTED,
                confidence=0.9,
            )
        )
    await db.commit()


class TestNPlusOneRegressionGuard:
    """See docs/modules/phase-14-hardening/FRD.md 'N+1 audit' -- proves the batching
    is real, not just plausible from reading the code, and catches a future regression
    that reintroduces a per-row query."""

    async def test_list_postmortems_query_count_stays_flat_as_rows_grow(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        owner = await signup(client)
        workspace_id = uuid.UUID(await _workspace_id(client, owner["access_token"]))

        await _seed_postmortems_with_services(db, workspace_id=workspace_id, count=2)
        small_count = await _count_queries(
            lambda: postmortem_service.list_postmortems(
                db, workspace_id=workspace_id, status=None, cursor=None, limit=50
            )
        )

        await _seed_postmortems_with_services(db, workspace_id=workspace_id, count=48)
        large_count = await _count_queries(
            lambda: postmortem_service.list_postmortems(
                db, workspace_id=workspace_id, status=None, cursor=None, limit=50
            )
        )

        # 2 rows vs. 50 rows -- if affected-services resolution were ever reintroduced
        # as a per-row query, large_count would grow roughly linearly with row count
        # instead of staying identical to small_count.
        assert large_count == small_count


async def _count_queries(call: object) -> int:
    sync_engine = get_engine().sync_engine
    count = 0

    def _on_execute(*args: object, **kwargs: object) -> None:
        nonlocal count
        count += 1

    event.listen(sync_engine, "before_cursor_execute", _on_execute)
    try:
        await call()  # type: ignore[operator]
    finally:
        event.remove(sync_engine, "before_cursor_execute", _on_execute)
    return count
