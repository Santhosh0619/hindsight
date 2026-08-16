"""Generated RBAC role-matrix sweep.

See docs/modules/phase-15-tests/FRD.md "test_rbac.py": iterates the real FastAPI app's
own route table to find every mutating endpoint nested under a workspace, and
mechanically asserts a viewer session gets 403 for every one of them -- so a new
mutating endpoint that forgets its role dependency fails this test automatically.

Verified empirically before writing this (see docs/decisions/0015-phase-15-tests.md):
this FastAPI version resolves a route's Depends(require_role(...)) check *before*
both Pydantic body validation and any resource-id lookup, so an empty body and a
syntactically-valid-but-nonexistent path-param id are both safe to send -- no
per-route fixture-creator registry is needed here, unlike test_tenant_isolation.py.
"""

import re
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.main import app
from app.models.workspace import WorkspaceMember, WorkspaceRole
from tests.conftest import auth_headers, signup

# Routes this generator can't (or doesn't need to) mechanically cover, with a reason --
# kept present (even when empty) so a future route that genuinely can't be covered has
# a documented place to go rather than silently vanishing from the sweep. Same
# structure as test_tenant_isolation.py's own.
KNOWN_UNCOVERED: dict[tuple[str, str], str] = {
    (
        "POST",
        "/workspaces/{workspace_id}/incidents/{incident_id}/brief/{brief_id}/feedback",
    ): (
        "Deliberately any-role (CurrentWorkspaceMember, not OwnerOrResponder) -- "
        "a viewer rating a brief 'helpful' isn't a privileged administrative action "
        "the way every other mutating route here is. Not an RBAC gap."
    ),
}

_MIN_EXPECTED_ROUTES = 15


def _mutating_workspace_routes() -> list[tuple[str, str]]:
    """Every (method, path) pair for a POST/PATCH/DELETE route nested under
    {workspace_id}."""
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        original_router = getattr(route, "original_router", None)
        if original_router is None:
            continue
        for sub_route in original_router.routes:
            path = getattr(sub_route, "path", None)
            methods = getattr(sub_route, "methods", None)
            if not path or not methods or "{workspace_id}" not in path:
                continue
            for method in methods & {"POST", "PATCH", "DELETE"}:
                routes.append((method, path))
    return routes


def test_the_generator_itself_finds_a_sane_number_of_routes() -> None:
    # Guards against the generator silently finding zero matches, which would make
    # every case below vacuously pass without asserting anything.
    found = _mutating_workspace_routes()
    assert len(found) >= _MIN_EXPECTED_ROUTES, found


def test_every_covered_or_explained_route_accounts_for_every_generated_route() -> None:
    found = set(_mutating_workspace_routes())
    accounted_for = found | set(KNOWN_UNCOVERED)  # every found route is coverable today
    missing = found - accounted_for
    assert missing == set(), (
        f"New mutating route(s) with no RBAC coverage and no KNOWN_UNCOVERED reason: {missing}"
    )


def _fill_path(path_template: str, workspace_id: str) -> str:
    params = re.findall(r"\{(\w+)\}", path_template)
    kwargs = {p: (workspace_id if p == "workspace_id" else str(uuid.uuid4())) for p in params}
    return path_template.format(**kwargs)


@pytest.mark.parametrize(
    ("method", "path_template"),
    sorted(set(_mutating_workspace_routes()) - set(KNOWN_UNCOVERED)),
)
async def test_a_viewer_gets_403_on_every_mutating_endpoint(
    client: AsyncClient, method: str, path_template: str
) -> None:
    owner = await signup(client)
    token = owner["access_token"]
    me = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    workspace_id = str(me.json()["memberships"][0]["workspace_id"])
    user_id = owner["user"]["id"]

    async with get_session_factory()() as db:
        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == uuid.UUID(workspace_id),
                WorkspaceMember.user_id == uuid.UUID(user_id),
            )
        )
        member = result.scalar_one()
        member.role = WorkspaceRole.VIEWER
        await db.commit()

    path = "/api/v1" + _fill_path(path_template, workspace_id)
    response = await client.request(method, path, headers=auth_headers(token), json={})

    assert response.status_code == 403, (method, path_template, response.text)
    assert response.json()["error"]["code"] == "forbidden", (method, path_template, response.text)
