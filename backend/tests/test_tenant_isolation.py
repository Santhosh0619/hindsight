"""Generated cross-tenant isolation sweep.

See docs/modules/phase-14-hardening/FRD.md "Generated tenant-isolation test": iterates
the real FastAPI app's own route table to find every GET route with a resource id
nested under {workspace_id}, and mechanically asserts that a session in workspace B
gets 404 (never a resource) when it requests one of workspace A's resources by id --
so a new endpoint that forgets its workspace_id filter fails this test automatically,
without anyone having to remember to hand-write a case for it.
"""

import re
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.main import app
from tests.conftest import auth_headers, signup

ResourceCreator = Callable[[AsyncClient, str, str], Awaitable[str]]


async def _workspace_id(client: AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    return str(response.json()["memberships"][0]["workspace_id"])


async def _create_service(client: AsyncClient, token: str, workspace_id: str) -> str:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/catalog/services",
        json={"name": "checkout-api", "tier": 1},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _create_postmortem(client: AsyncClient, token: str, workspace_id: str) -> str:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/postmortems",
        json={"title": "t", "raw_text": "incident happened"},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _create_incident(client: AsyncClient, token: str, workspace_id: str) -> str:
    response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents",
        json={"title": "t", "raw_alert_text": "checkout-api is throwing 500s"},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _create_agent_run(client: AsyncClient, token: str, workspace_id: str) -> str:
    incident_id = await _create_incident(client, token, workspace_id)
    brief_response = await client.post(
        f"/api/v1/workspaces/{workspace_id}/incidents/{incident_id}/brief",
        headers=auth_headers(token),
    )
    assert brief_response.status_code == 200, brief_response.text
    runs_response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/agent-runs", headers=auth_headers(token)
    )
    return str(runs_response.json()["items"][0]["id"])


# Keyed by the route's own path template (not just its trailing param name -- both
# /evaluation/runs/{run_id} and /agent-runs/{run_id} use "run_id" but need different
# fixtures) so each entry is unambiguous about which resource it creates.
_CREATORS: dict[str, ResourceCreator] = {
    "/workspaces/{workspace_id}/catalog/services/{service_id}": _create_service,
    "/workspaces/{workspace_id}/catalog/services/{service_id}/blast-radius": _create_service,
    "/workspaces/{workspace_id}/postmortems/{postmortem_id}": _create_postmortem,
    "/workspaces/{workspace_id}/postmortems/{postmortem_id}/status": _create_postmortem,
    "/workspaces/{workspace_id}/incidents/{incident_id}": _create_incident,
    "/workspaces/{workspace_id}/incidents/{incident_id}/briefs": _create_incident,
    # stream_brief looks up the incident (and 404s on a cross-tenant id) before ever
    # constructing the EventSourceResponse, so a plain GET-and-expect-404 covers it
    # exactly like every other route here -- no SSE-specific handling needed.
    "/workspaces/{workspace_id}/incidents/{incident_id}/brief/stream": _create_incident,
    "/workspaces/{workspace_id}/agent-runs/{run_id}": _create_agent_run,
}

# Routes this generator can't (or doesn't need to) mechanically cover, with a reason --
# keeps the generator's own coverage visible rather than silently partial.
KNOWN_UNCOVERED = {
    "/workspaces/{workspace_id}/evaluation/runs/{run_id}": (
        "EvalRun rows are only created by the CLI/seed script, not any API route; "
        "already covered by test_evaluation_api.py::"
        "test_get_eval_run_detail_404s_across_workspaces"
    ),
}

_MIN_EXPECTED_ROUTES = 5


def _nested_get_routes() -> list[str]:
    """Every GET route whose path has a resource id nested after {workspace_id}."""
    paths: list[str] = []
    for route in app.routes:
        original_router = getattr(route, "original_router", None)
        if original_router is None:
            continue
        for sub_route in original_router.routes:
            path = getattr(sub_route, "path", None)
            methods = getattr(sub_route, "methods", None)
            if not path or not methods or "GET" not in methods:
                continue
            if "{workspace_id}" not in path:
                continue
            params = re.findall(r"\{(\w+)\}", path)
            if len(params) >= 2:
                paths.append(path)
    return paths


def test_the_generator_itself_finds_a_sane_number_of_routes() -> None:
    # Guards against the generator silently finding zero matches (e.g. a FastAPI
    # internal-routing change breaking _nested_get_routes' own traversal), which would
    # make every test below vacuously "pass" without asserting anything.
    found = _nested_get_routes()
    assert len(found) >= _MIN_EXPECTED_ROUTES, found


def test_every_covered_or_explained_route_accounts_for_every_generated_route() -> None:
    found = set(_nested_get_routes())
    accounted_for = set(_CREATORS) | set(KNOWN_UNCOVERED)
    missing = found - accounted_for
    assert missing == set(), (
        f"New nested-resource GET route(s) with no tenant-isolation fixture and no "
        f"KNOWN_UNCOVERED reason: {missing}"
    )


@pytest.mark.parametrize("path_template", sorted(_CREATORS))
async def test_a_second_workspace_cannot_read_the_first_workspaces_resource(
    client: AsyncClient, path_template: str
) -> None:
    creator = _CREATORS[path_template]

    owner_a = await signup(client)
    token_a = owner_a["access_token"]
    workspace_a = await _workspace_id(client, token_a)
    resource_id = await creator(client, token_a, workspace_a)

    owner_b = await signup(client)
    token_b = owner_b["access_token"]
    workspace_b = await _workspace_id(client, token_b)

    # _CREATORS/_nested_get_routes() key on the router's own unprefixed path template
    # (matching what app.routes' original_router.routes exposes) -- the real mounted
    # path needs the /api/v1 prefix app.main adds via include_router(..., prefix=
    # "/api/v1"), or this request hits no route at all and 404s on Starlette's own
    # generic "not found" regardless of whether the app's tenant-isolation logic
    # works, making the assertion below vacuous.
    path = "/api/v1" + path_template.format(
        workspace_id=workspace_b, **_id_kwargs(path_template, resource_id)
    )
    response = await client.get(path, headers=auth_headers(token_b))
    assert response.status_code == 404, (path_template, response.text)
    # Confirms this really is the app's own NotFoundError envelope, not Starlette's
    # generic 404 for an unmatched route -- the exact distinction a missing /api/v1
    # prefix would otherwise hide.
    assert response.json()["error"]["code"] == "not_found", (path_template, response.text)


def _id_kwargs(path_template: str, resource_id: str) -> dict[str, str]:
    # Every template in _CREATORS has exactly one non-workspace_id param -- fill
    # whichever one it is with the real resource id.
    params = re.findall(r"\{(\w+)\}", path_template)
    other = next(p for p in params if p != "workspace_id")
    return {other: resource_id}
