# FRD: Documentation

## API Endpoints (Backend — FastAPI)

None. No route changes.

## React Components (Frontend)

None. No component changes.

## Data Model Changes

None. `docs/data-model.md` documents the existing schema; it doesn't change it.

## Internal Architecture

### `README.md` (rewritten)

Section order, matching Master-Prompt.md's Phase 17 spec with items 1 and 2's
image/video requirement dropped per the PRD's scope decision:

1. Title, one-line pitch, status line. No badges yet (CI badge needs a public repo URL
   confirmed working from a fresh clone; added once that's verified, not asserted).
2. Live demo line — placeholder text noting the link lands after Phase 18 deploys,
   not a dead link pointing nowhere.
3. The problem, four sentences, drawn from plan.md §2's 2am scenario, not
   paraphrased.
4. What it does — three bullets (brief with citations, blast radius, hybrid search
   attribution), no screenshots per scope decision.
5. Evaluation table — real numbers from a fresh run of
   `app.services.evaluation.cli --mode all` against the seeded corpus (20 eval cases),
   not copied from ADR 0012. Includes the honest tied-ablation finding as prose, not
   just the table, since the number alone doesn't explain why it's not a hidden bug.
6. Architecture — condensed version of `docs/architecture.md`'s diagram, with a link
   to the full doc.
7. Agent pipeline — six nodes, the corrective loop, why LangGraph over a linear
   chain, condensed from `docs/architecture.md`.
8. Tech stack table — drawn from plan.md §10, cross-checked against
   `backend/pyproject.toml`/`frontend/package.json` for anything that's since changed.
9. Quick start — `git clone`, `cp .env.example .env`, `make dev`, `make seed`. Verified
   against the current `Makefile`/`.env.example`, not assumed unchanged since Phase 1.
10. Limitations — the same honest weaknesses plan.md §17 question 12 names outright:
    synthetic, self-authored eval set; fixed failure-mode taxonomy; heuristic service
    linking; retrieval quality bounded by postmortem quality.
11. Project structure, roadmap (remaining phases), license (MIT).

### `docs/architecture.md` (new)

- System diagram (frontend / API / queue+worker / LangGraph pipeline / Postgres /
  LLM router), redrawn from plan.md §7, cross-checked against `app/main.py`'s actual
  router wiring and `docker-compose.yml`'s actual services rather than copied
  unverified.
- "Why one database instead of three" — the four reasons from plan.md §7 (graph size/
  recursive-CTE cost, Neo4j AuraDB's 3-day auto-pause, cross-store transactional
  consistency, one backup/pool/migration path), plus the `GraphStore` protocol as the
  documented swap point and the scale threshold at which a dedicated graph database
  would earn its place.
- The agent pipeline in full — six nodes, the three-way retrieval fusion, the
  citation-grounded analyst step, the critic's corrective loop and its stop condition
  (`critic_threshold`, `max_correction_passes`), all cross-checked against
  `app/agents/build_graph.py`, `app/agents/edges.py`, and `app/core/config.py`'s actual
  field names and defaults rather than plan.md's original projected values.
- The prompt-injection guardrail (postmortems are untrusted text; ingest-time
  screening plus analyst-prompt delimiting) as its own subsection, since plan.md
  explicitly calls this out as a real differentiator most portfolio RAG projects skip.

### `docs/data-model.md` (new)

- Every table from `backend/app/models/*.py`, grouped by domain (identity/workspace,
  catalog, postmortems, incidents/briefs, agent runs, evaluation, jobs/cache) — read
  directly from the SQLAlchemy model classes, not transcribed from plan.md §8's
  pre-implementation sketch, since 16 phases of real work is enough for drift.
- The indexes that matter (HNSW on the embedding column, GIN on the full-text column,
  the tenant-scoped composite indexes, the queue's claim-query partial index) — quoted
  from the actual Alembic migrations, not asserted.
- The one deliberate cross-cutting rule this whole schema depends on:
  `workspace_id` on every tenant-scoped table, enforced in the repository layer — with
  a pointer to `test_tenant_isolation.py` (Phase 14) as the thing that actually proves
  it, not just states it.

## Dependencies

- Calls: the real evaluation harness (`app.services.evaluation.cli`), the real seed
  fixtures (`backend/app/seed/fixtures/*.json`), the real SQLAlchemy models and
  Alembic migrations — read-only, for accurate content, not modified.
- Called by: nothing — this phase produces documentation, not code any other module
  depends on.

## Edge Cases & Error Handling

- **A number changes between when it's written and when this phase's PR is reviewed**
  (e.g. a later commit on this same branch touches the seed fixtures): re-run the
  evaluation harness and re-count the fixtures immediately before the final commit,
  not trust an earlier session's numbers.
- **plan.md's projected schema and the real schema disagree**: the real schema wins,
  always — `docs/data-model.md` documents what Alembic would produce today, not what
  an 18-phase-old planning document guessed it would look like.
