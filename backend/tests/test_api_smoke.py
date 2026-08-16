"""Generated endpoint smoke sweep.

See docs/modules/phase-15-tests/FRD.md "test_api_smoke.py": iterates every route the
real FastAPI app actually serves and asserts none of them ever answers with a bare
500 for a minimal, boundary-shaped request (empty body, a real workspace id, random
UUIDs for every other path param) -- a shallow "this route is wired up and fails
cleanly" check, not a substitute for each module's own deep behavioral tests.
"""

import re
import uuid

import pytest
from httpx import AsyncClient

from app.main import app
from tests.conftest import auth_headers, signup

_MIN_EXPECTED_ROUTES = 50

# Routes this generator can't meaningfully exercise the same generic way as every
# other one, with a reason -- kept explicit rather than silently skipped.
KNOWN_UNCOVERED = {
    ("POST", "/ingest/postmortem"): (
        "Authenticated by X-API-Key, not a session Bearer token -- already covered "
        "by test_ingest_api.py's own dedicated checkpoint test."
    ),
}


def _all_routes() -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        original_router = getattr(route, "original_router", None)
        if original_router is None:
            continue
        for sub_route in original_router.routes:
            path = getattr(sub_route, "path", None)
            methods = getattr(sub_route, "methods", None)
            if not path or not methods:
                continue
            for method in methods:
                if method == "HEAD":
                    continue
                routes.append((method, path))
    return routes


def test_the_generator_itself_finds_a_sane_number_of_routes() -> None:
    found = _all_routes()
    assert len(found) >= _MIN_EXPECTED_ROUTES, found


def test_every_covered_or_explained_route_accounts_for_every_generated_route() -> None:
    found = set(_all_routes())
    accounted_for = found | set(KNOWN_UNCOVERED)
    missing = found - accounted_for
    assert missing == set(), (
        f"New route(s) with no smoke coverage and no KNOWN_UNCOVERED reason: {missing}"
    )


def _fill_path(path_template: str, workspace_id: str) -> str:
    params = re.findall(r"\{(\w+)\}", path_template)
    kwargs = {p: (workspace_id if p == "workspace_id" else str(uuid.uuid4())) for p in params}
    return path_template.format(**kwargs)


_METHODS_WITH_BODY = {"POST", "PATCH", "PUT"}


@pytest.mark.parametrize(
    ("method", "path_template"),
    sorted(set(_all_routes()) - set(KNOWN_UNCOVERED)),
)
async def test_every_route_answers_without_a_bare_500(
    client: AsyncClient, method: str, path_template: str
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    me = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    workspace_id = str(me.json()["memberships"][0]["workspace_id"])

    path = _fill_path(path_template, workspace_id)
    kwargs: dict[str, object] = {"headers": auth_headers(token)}
    if method in _METHODS_WITH_BODY:
        kwargs["json"] = {}

    response = await client.request(method, path, **kwargs)  # type: ignore[arg-type]

    assert response.status_code < 500, (method, path_template, response.status_code, response.text)
