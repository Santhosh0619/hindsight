import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.models.catalog import Service, ServiceEdge, Team
from app.models.evaluation import EvalCase
from app.models.incident import Brief, Incident
from app.models.postmortem import FactType, Postmortem, PostmortemChunk, PostmortemFact
from app.models.workspace import Workspace
from app.seed import seed as seed_module
from app.seed.seed import FIXTURES_DIR

# generate_postmortems.py's _facts_for() mapping -- every fact this fixture produces
# is expected to cite a chunk whose section_label matches this table.
_EXPECTED_SECTION_BY_FACT_TYPE = {
    FactType.TRIGGER: "Summary",
    FactType.ROOT_CAUSE: "Root Cause",
    FactType.REMEDIATION: "Remediation",
    FactType.CONTRIBUTING_FACTOR: "Impact",
    FactType.DETECTION_GAP: "Detection",
}

# generate_catalog.py's EDGES are engineered so these two services get exactly one
# incoming edge each -- deliberate single points of failure with no redundant path.
_SPOF_SERVICE_NAMES = ["session-service", "payment-gateway-adapter"]

# The demo workspace is shared with test_demo_mode.py, which -- by exercising the
# real feature end-to-end -- legitimately creates its own extra incidents/briefs in
# it (a demo guest always joins this one workspace, by design). Counting seed.py's
# own rows by the exact titles its fixtures declare, rather than raw table totals,
# keeps this test correct regardless of what else has run against the same
# workspace, in whatever order.
_SEEDED_INCIDENT_TITLES = [
    entry["title"] for entry in json.loads((FIXTURES_DIR / "incidents.json").read_text())
]


async def _demo_workspace_id(db: AsyncSession) -> Any:
    result = await db.execute(select(Workspace.id).where(Workspace.is_demo.is_(True)).limit(1))
    return result.scalar_one()


async def _counts(db: AsyncSession, workspace_id: Any) -> dict[str, int]:
    async def _count(model: Any) -> int:
        result = await db.execute(
            select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
        )
        return result.scalar_one()

    seeded_incidents_result = await db.execute(
        select(func.count())
        .select_from(Incident)
        .where(Incident.workspace_id == workspace_id, Incident.title.in_(_SEEDED_INCIDENT_TITLES))
    )
    seeded_briefs_result = await db.execute(
        select(func.count())
        .select_from(Brief)
        .join(Incident, Incident.id == Brief.incident_id)
        .where(
            Incident.workspace_id == workspace_id,
            Incident.title.in_(_SEEDED_INCIDENT_TITLES),
            Brief.from_cache.is_(True),
        )
    )
    return {
        "teams": await _count(Team),
        "services": await _count(Service),
        "edges": await _count(ServiceEdge),
        "postmortems": await _count(Postmortem),
        "eval_cases": await _count(EvalCase),
        "seeded_incidents": seeded_incidents_result.scalar_one(),
        "seeded_briefs": seeded_briefs_result.scalar_one(),
    }


_EXPECTED_COUNTS = {
    "teams": 8,
    "services": 40,
    "edges": 57,
    "postmortems": 80,
    "eval_cases": 20,
    "seeded_incidents": 12,
    "seeded_briefs": 8,
}


async def test_seed_loader_produces_documented_counts_and_is_idempotent() -> None:
    await seed_module.run()

    session_factory = get_session_factory()
    async with session_factory() as db:
        workspace_id = await _demo_workspace_id(db)
        first_run_counts = await _counts(db, workspace_id)
    assert first_run_counts == _EXPECTED_COUNTS

    await seed_module.run()

    session_factory = get_session_factory()
    async with session_factory() as db:
        second_run_counts = await _counts(db, workspace_id)
    assert second_run_counts == first_run_counts


async def test_seed_facts_cite_a_chunk_whose_section_matches_the_fact_type() -> None:
    await seed_module.run()

    session_factory = get_session_factory()
    async with session_factory() as db:
        workspace_id = await _demo_workspace_id(db)
        result = await db.execute(
            select(PostmortemFact.fact_type, PostmortemChunk.section_label)
            .join(PostmortemChunk, PostmortemChunk.id == PostmortemFact.source_chunk_id)
            .join(Postmortem, Postmortem.id == PostmortemFact.postmortem_id)
            .where(Postmortem.workspace_id == workspace_id)
        )
        rows = result.all()

    assert len(rows) == 324
    for fact_type, section_label in rows:
        assert section_label == _EXPECTED_SECTION_BY_FACT_TYPE[fact_type]


async def test_seed_deliberate_spofs_have_exactly_one_incoming_edge() -> None:
    await seed_module.run()

    session_factory = get_session_factory()
    async with session_factory() as db:
        workspace_id = await _demo_workspace_id(db)
        for name in _SPOF_SERVICE_NAMES:
            service_result = await db.execute(
                select(Service.id).where(Service.workspace_id == workspace_id, Service.name == name)
            )
            service_id = service_result.scalar_one()
            incoming_result = await db.execute(
                select(func.count())
                .select_from(ServiceEdge)
                .where(ServiceEdge.to_service_id == service_id)
            )
            assert incoming_result.scalar_one() == 1, (
                f"{name} should have exactly one incoming edge"
            )
