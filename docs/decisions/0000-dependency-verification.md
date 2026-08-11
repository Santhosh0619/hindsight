# ADR 0000: Dependency Verification (Phase 0 Pre-Flight)

## Context

`plan.md` was written assuming certain library APIs and a certain Gemini model ID.
Library surfaces move fast — `pydantic-ai`, `langgraph`, and Gemini's free-tier model
lineup have all changed since the plan was drafted. Master-Prompt.md's Phase 0 requires
verifying four things against what is actually installed/available before any
application code is written, so the codebase is built against reality rather than a
stale assumption.

Verification was done with the exact versions that `pip` resolves today, installed into
a throwaway virtualenv (not committed — `backend/pyproject.toml` will pin these properly
in Phase 1), plus a live probe against the `pgvector/pgvector:pg16` image this project
already uses in `docker-compose.yml`.

## Findings

### 1. `pydantic-ai` — version installed: `2.27.1`

The plan's assumption of "agents with typed result models" holds, but the calling
convention has changed name:

- Construct with `Agent(model, output_type=SomeModel)` — the parameter is **`output_type`**,
  not `result_type` (an older/deprecated name from early pydantic-ai versions).
- Run with `agent.run_sync(prompt)` / `await agent.run(prompt)` → returns an
  `AgentRunResult[T]`. The typed value is on **`result.output`** (a dataclass field),
  not `result.data`.
- Confirmed by direct construction and `inspect.signature()` against the installed
  package — see verification commands below.

**Deviation from plan.md:** none functionally — typed structured output works exactly as
assumed. Only the attribute/parameter names differ (`output_type`/`.output` instead of
`result_type`/`.data`). All Phase 6/8 code will use the current names.

### 2. LangGraph Postgres checkpointer

- Package name: **`langgraph-checkpoint-postgres`** (confirmed importable as
  `langgraph.checkpoint.postgres` / `langgraph.checkpoint.postgres.aio`).
- Version installed: `3.1.2` (with `langgraph` `1.2.11` and `langgraph-checkpoint` `4.2.0`).
- Class: `AsyncPostgresSaver`. Connection API:
  `async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:` (it's an async
  context manager, not a plain constructor), then `await saver.setup()` once to create
  its tables (it ships its own `MIGRATIONS`, separate from our Alembic migrations).
- **Hard runtime dependency:** requires `psycopg` with a compiled/binary backend. On a
  system without `libpq` installed, plain `psycopg` raises `ImportError: no pq wrapper
  available` at import time. Fix: depend on **`psycopg[binary]`**, not bare `psycopg`, in
  `backend/pyproject.toml`. This must be added explicitly — it does not come in
  transitively from `langgraph-checkpoint-postgres`.
- Postgres checkpointer is available and works — no need to fall back to
  `langgraph-checkpoint-sqlite` (also installed and confirmed importable, kept as the
  documented fallback per Master-Prompt.md if a future host can't run psycopg).

**Deviation from plan.md:** must add `psycopg[binary]` as an explicit dependency
alongside `langgraph-checkpoint-postgres`.

### 3. Gemini free-tier model ID

Verified via web search (Google's own rate-limit page requires an AI Studio login to
show live per-model numbers, so it could not be fetched directly) against multiple 2026
sources. As of April 2026, Google moved Pro-series models to paid-only; the free tier is
Flash/Flash-Lite class only. Free-tier-eligible model IDs as of this check: Gemini 2.5
Flash, 2.5 Flash-Lite, 2.5 Pro (search results conflict on Pro; treat as unconfirmed),
3 Flash Preview, 3.1 Flash-Lite, and the legacy 2.0 Flash/Flash-Lite.

**Decision:** default `LLM_MODEL` to **`gemini-2.5-flash`** — it is the most-cited stable
(non-preview) free-tier model across sources, at roughly 10 RPM / 250 requests-per-day on
the free tier. Preview models (e.g. `gemini-3-flash-preview`) are deliberately avoided as
the default since preview model IDs and quotas change/retire with less notice.

**This is not hardcoded** — `LLM_MODEL` is a `Settings` field with this documented
default and a full env override (`plan.md` §10 / Master-Prompt.md Phase 1 already
require this). Per Master-Prompt.md's error-recovery rule: if a Gemini call ever rejects
the configured model ID, surface a clear error telling the operator to check
https://aistudio.google.com for the current ID — never silently swap providers.

### 4. pgvector index type

Probed directly against the project's actual `pgvector/pgvector:pg16` image:

```
pgvector extension version: 0.8.6
PostgreSQL version: 16.14 (Debian)
CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)  →  succeeded
```

HNSW has been supported since pgvector 0.5.0; 0.8.6 is well past that. **No IVFFlat
fallback is needed** — HNSW will be used for `postmortem_chunks.embedding` and
`semantic_cache.embedding` as planned.

## Decision

Proceed to Phase 1 using:
- `pydantic-ai` with `output_type` / `.output` (current API, not the plan's assumed
  `result_type` / `.data`).
- `langgraph-checkpoint-postgres` + explicit `psycopg[binary]` dependency for the
  Postgres checkpointer.
- `LLM_MODEL` default of `gemini-2.5-flash`, fully overridable via env, re-verified at
  AI Studio before Phase 6/8 actually issue LLM calls.
- HNSW indexes on all vector columns, no IVFFlat fallback path needed.

## Alternatives rejected

- Pinning to whatever model/API surface `plan.md` originally assumed, unverified — would
  guarantee broken imports and hallucinated method names on the very first `pip install`.
- Falling back to `langgraph-checkpoint-sqlite` by default — rejected because the
  Postgres saver works and keeps checkpoints in the same database as everything else
  (one backup, one connection pool — the same rationale `plan.md` §7 gives for not
  adding a second data store).

## Verification commands run

```bash
python -m venv <throwaway venv>
pip install pydantic-ai langgraph langgraph-checkpoint-postgres langgraph-checkpoint-sqlite \
            langchain langchain-community "psycopg[binary]"

python -c "from pydantic_ai import Agent; import inspect; print(inspect.signature(Agent.__init__))"
python -c "from pydantic_ai import AgentRunResult; print(AgentRunResult.__dataclass_fields__.keys())"
python -c "from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver; import inspect; \
           print(inspect.signature(AsyncPostgresSaver.from_conn_string))"

docker compose up db -d
docker compose exec db psql -U postgres -d hindsight -c \
  "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname='vector';"
docker compose exec db psql -U postgres -d hindsight -c \
  "CREATE TABLE hnsw_probe (id serial primary key, embedding vector(3));
   CREATE INDEX hnsw_probe_idx ON hnsw_probe USING hnsw (embedding vector_cosine_ops);
   DROP TABLE hnsw_probe;"
docker compose down
```
