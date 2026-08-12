from httpx import AsyncClient

from app.services.rate_limit import TokenBucket
from tests.conftest import auth_headers, signup, unique_email


async def test_signup_creates_user_and_personal_workspace(client: AsyncClient) -> None:
    body = await signup(client, full_name="Alice Signup")

    assert body["token_type"] == "bearer"
    assert body["user"]["full_name"] == "Alice Signup"
    assert body["user"]["is_demo"] is False
    assert "refresh_token" in client.cookies


async def test_signup_duplicate_email_conflicts(client: AsyncClient) -> None:
    email = unique_email()
    await signup(client, email=email)

    response = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "correcthorse123", "full_name": "Someone Else"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_login_happy_path(client: AsyncClient) -> None:
    email = unique_email()
    await signup(client, email=email, password="correcthorse123")

    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correcthorse123"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == email


async def test_login_wrong_password_and_unknown_email_give_same_error(
    client: AsyncClient,
) -> None:
    email = unique_email()
    await signup(client, email=email, password="correcthorse123")

    wrong_password = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
    )
    unknown_email = await client.post(
        "/api/v1/auth/login", json={"email": unique_email(), "password": "whatever123"}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_me_returns_user_and_memberships(client: AsyncClient) -> None:
    body = await signup(client)

    response = await client.get("/api/v1/auth/me", headers=auth_headers(body["access_token"]))

    assert response.status_code == 200
    me = response.json()
    assert me["user"]["id"] == body["user"]["id"]
    assert len(me["memberships"]) == 1
    assert me["memberships"][0]["role"] == "owner"


async def test_refresh_rotates_the_cookie(client: AsyncClient) -> None:
    await signup(client)
    first_cookie = client.cookies.get("refresh_token")

    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    second_cookie = client.cookies.get("refresh_token")
    assert second_cookie is not None
    assert second_cookie != first_cookie


async def test_refresh_reuse_revokes_the_whole_family(client: AsyncClient) -> None:
    await signup(client)
    first_cookie = client.cookies.get("refresh_token")
    assert first_cookie is not None

    await client.post("/api/v1/auth/refresh")
    second_cookie = client.cookies.get("refresh_token")
    assert second_cookie is not None

    client.cookies.set("refresh_token", first_cookie, path="/api/v1/auth")
    reuse_response = await client.post("/api/v1/auth/refresh")
    assert reuse_response.status_code == 401
    assert "already been used" in reuse_response.json()["error"]["message"]

    client.cookies.set("refresh_token", second_cookie, path="/api/v1/auth")
    also_revoked_response = await client.post("/api/v1/auth/refresh")
    assert also_revoked_response.status_code == 401


async def test_refresh_without_cookie_is_unauthorized(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 401


async def test_logout_then_refresh_fails(client: AsyncClient) -> None:
    await signup(client)

    logout_response = await client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204

    refresh_response = await client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401


async def test_logout_without_cookie_is_a_no_op(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 204


async def test_demo_guest_gets_a_working_session_with_no_prior_signup(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/v1/auth/demo")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["is_demo"] is True

    me = await client.get("/api/v1/auth/me", headers=auth_headers(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["memberships"][0]["role"] == "viewer"


def test_token_bucket_blocks_after_capacity_is_exhausted() -> None:
    bucket = TokenBucket(capacity=3, refill_seconds=3600)

    results = [bucket.consume("1.2.3.4") for _ in range(4)]

    assert results == [True, True, True, False]


def test_token_bucket_tracks_keys_independently() -> None:
    bucket = TokenBucket(capacity=1, refill_seconds=3600)

    assert bucket.consume("a") is True
    assert bucket.consume("b") is True
    assert bucket.consume("a") is False
