"""`make eval` / `python -m app.services.evaluation.cli`'s real target -- an operator
command, never reachable from a request handler (the groundedness metric makes a real
LLM call). `--mode all` (the default) runs the three ablation modes back to back and
prints the comparison table Master-Prompt.md's Phase 12 checkpoint wants pasted into
the README; a single mode prints that run's own metrics plus a per-case drill-down,
failing cases first.
"""

import argparse
import asyncio
import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, get_session_factory
from app.models.evaluation import EvalRun
from app.models.workspace import Workspace
from app.schemas.evaluation import EvalCaseResultOut
from app.services import evaluation_service
from app.services.evaluation.runner import ABLATION_MODES, AblationMode, run_eval
from app.services.llm.router import build_router
from app.services.postgres_graph_store import PostgresGraphStore

logger = get_logger(__name__)

CliMode = AblationMode | Literal["all"]

_MODE_LABELS: dict[AblationMode, str] = {
    "vector": "Vector only",
    "vector_bm25": "Vector + BM25",
    "full": "Vector + BM25 + Graph (full)",
}


def _fmt(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "—"


async def _resolve_workspace_id(db: AsyncSession, workspace_id: uuid.UUID | None) -> uuid.UUID:
    if workspace_id is not None:
        return workspace_id
    result = await db.execute(select(Workspace.id).where(Workspace.is_demo.is_(True)).limit(1))
    found = result.scalar_one_or_none()
    if found is None:
        raise SystemExit("No demo workspace found -- run `make seed` first, or pass --workspace-id")
    return found


def _print_case_results(results: list[EvalCaseResultOut]) -> None:
    ordered = sorted(results, key=lambda r: r.passed)  # failing (False) sorts first
    print(f"\n{'Case':<32}{'Rank':>8}{'Groundedness':>16}{'Passed':>10}")
    for result in ordered:
        rank = str(result.rank_of_first_hit) if result.rank_of_first_hit is not None else "miss"
        print(
            f"{result.case_name:<32}{rank:>8}{_fmt(result.groundedness):>16}"
            f"{'yes' if result.passed else 'no':>10}"
        )


def _print_run(mode: str, run: EvalRun, results: list[EvalCaseResultOut]) -> None:
    print(f"\nmode={mode}")
    print(f"  recall@1           {_fmt(run.recall_at_1)}")
    print(f"  recall@5           {_fmt(run.recall_at_5)}")
    print(f"  mrr                {_fmt(run.mrr)}")
    print(f"  citation_validity  {_fmt(run.citation_validity)}")
    groundedness_note = (
        "" if run.groundedness is not None else "  (skipped -- no LLM key configured)"
    )
    print(f"  groundedness       {_fmt(run.groundedness)}{groundedness_note}")
    print(f"  cases_run          {run.cases_run}")
    _print_case_results(results)


def _print_ablation_table(runs: dict[AblationMode, EvalRun]) -> None:
    print("\nAblation comparison")
    print(f"{'Configuration':<32}{'recall@1':>10}{'recall@5':>10}{'mrr':>10}")
    for mode in ABLATION_MODES:
        run = runs[mode]
        print(
            f"{_MODE_LABELS[mode]:<32}{_fmt(run.recall_at_1):>10}"
            f"{_fmt(run.recall_at_5):>10}{_fmt(run.mrr):>10}"
        )

    print("\nMarkdown (paste into README):\n")
    print("| Configuration | recall@5 | MRR |")
    print("|---|---|---|")
    for mode in ABLATION_MODES:
        run = runs[mode]
        print(f"| {_MODE_LABELS[mode]} | {_fmt(run.recall_at_5)} | {_fmt(run.mrr)} |")


async def _run(mode: CliMode, workspace_id: uuid.UUID | None, top_k: int) -> None:
    configure_logging()
    settings = get_settings()
    session_factory = get_session_factory()
    router = build_router(settings)

    async with session_factory() as db:
        resolved_workspace_id = await _resolve_workspace_id(db, workspace_id)
        graph_store = PostgresGraphStore(db)

        if mode == "all":
            runs: dict[AblationMode, EvalRun] = {}
            for ablation_mode in ABLATION_MODES:
                runs[ablation_mode] = await run_eval(
                    db,
                    graph_store,
                    router,
                    workspace_id=resolved_workspace_id,
                    mode=ablation_mode,
                    top_k=top_k,
                    llm_configured=settings.llm_configured,
                )
            _print_ablation_table(runs)
        else:
            run = await run_eval(
                db,
                graph_store,
                router,
                workspace_id=resolved_workspace_id,
                mode=mode,
                top_k=top_k,
                llm_configured=settings.llm_configured,
            )
            detail = await evaluation_service.get_run_detail(
                db, workspace_id=resolved_workspace_id, run_id=run.id
            )
            _print_run(mode, run, detail.results)

    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Hindsight evaluation harness")
    parser.add_argument("--mode", choices=["vector", "vector_bm25", "full", "all"], default="all")
    parser.add_argument("--workspace-id", type=uuid.UUID, default=None)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()
    mode: CliMode = args.mode
    asyncio.run(_run(mode, args.workspace_id, args.top_k))


if __name__ == "__main__":
    main()
