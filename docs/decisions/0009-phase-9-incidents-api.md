# ADR 0009: Incidents API + The Money Screen — A Startup-Time Deadlock, Session Lifecycle, and Schema Boundaries

## 1. `AsyncPostgresSaver.setup()` moved from per-request to app startup — a real deadlock, not a slow query

**Context.** ADR 0008 §6 deliberately kept the checkpointer out of `app/main.py`'s
lifespan: no request path needed it yet, so holding a second Postgres connection pool
open app-wide for zero present benefit was the wrong call. Phase 9's `generate_brief`
and `stream_brief_generation` became that first real caller, each building a fresh
`AsyncPostgresSaver` and calling `await saver.setup()` before every graph run, matching
the same lazy-construction discipline as the LLM router and semantic cache.

**What actually happened.** `e2e/tests/incidents.spec.ts`, run against `docker-
compose.test.yml`'s always-freshly-created `db-test` service, hung indefinitely on the
very first brief-generation request — no `node_start` event, no error, nothing, for
over a minute, confirmed independent of the browser via a plain Node `fetch()` against
the raw SSE endpoint. `pg_stat_activity` on `db-test` showed the actual mechanism: a
`CREATE INDEX CONCURRENTLY IF NOT EXISTS checkpoint_writes_thread_id_idx` (part of
`AsyncPostgresSaver.setup()`'s first-ever table creation) sitting in `Lock/virtualxid`
wait, while the *same request's own* `AsyncSession` sat `idle in transaction` — opened
by `_start_agent_run`'s `db.refresh(run)` (SQLAlchemy autobegins a transaction on any
statement after a commit) and not closed until `_finish_agent_run`'s commit, which
can't happen until the graph — which is waiting on `setup()` — finishes. `CREATE INDEX
CONCURRENTLY` must wait for every transaction open anywhere on the database at the
moment it starts, including idle ones; this request's session was one of them. Circular
wait, not slowness — the request would have hung forever if the client hadn't given up.

This never surfaced against this project's normal dev Postgres (`docker-compose.yml`'s
`db`, months old at this point) because the checkpoint tables already existed from
earlier manual runs — `IF NOT EXISTS` short-circuited before the wait could ever start.
Only a genuinely fresh database, which only the e2e stack's `db-test` provides, could
have caught this; it's also a real production risk, since any brand-new deployment's
first-ever brief-generation request under any concurrent load would hit the identical
deadlock.

**Decision.** Run `saver.setup()` exactly once, in `app/main.py`'s lifespan, before the
app starts accepting requests — no request-scoped session can be mid-transaction at
that point, so the wait this DDL performs is always against an empty set and returns
immediately. `generate_brief`/`stream_brief_generation` still build a fresh
`AsyncPostgresSaver` per call for the actual graph run (ADR 0008 §6's reasoning against
a held-open app-level *saver* still applies — this only moves the one-time, idempotent
*table/index creation* earlier, not the saver's lifetime). Verified by rebuilding the
e2e stack from a clean `db-test` and running the full incidents flow: all four tests
pass in under 7 seconds each, versus indefinite hangs before the fix.

## 2. `stream_brief`'s SSE generator owns a session scoped to its own lifetime, not the request's

**Context.** FastAPI's per-request `db` dependency is closed by its own
`AsyncExitStack` as soon as the route handler returns the response object — before
Starlette starts iterating an `EventSourceResponse`'s body. A first draft of
`stream_brief` closed over that request-scoped session inside its generator, which
worked in casual manual testing (the closure captured the object, and nothing raced
badly enough to surface it every time) but is wrong on inspection: every DB write the
generator performs happens after the session it's using has already been torn down.

**Decision.** The generator opens its own session via `get_session_factory()`, scoped
to the SSE body's actual lifetime, and builds its own `PostgresGraphStore`/`LLMRouter`
against it — mirroring the same "don't borrow a session whose owner has already moved
on" fix Phase 8 made for `stream_graph_events`'s `AgentRunStep` writes (ADR 0008 §4).
Verified with an HTTP-level test (`test_stream_brief_endpoint_returns_a_real_sse_event_
sequence`) that drives the real ASGI route via `client.stream(...)`, not the service
function directly — the earlier service-level tests bypassed the exact layer this bug
lived in, the same lesson ADR 0008 §4 already drew about design-only review versus
actually running the code.

## 3. The graph's internal schemas and the HTTP API's response schemas are deliberately different layers

**Context.** Phase 8's `Citation`, `CandidateMatch`, `Hypothesis`, `RunbookStepDraft`,
and `graph_store.BlastRadius` carry only what the graph itself needs to reason and to
persist as JSONB — ids, scores, offsets. None of that is renderable on its own; F5/F6
need postmortem titles, chunk text, and resolved service names/tiers.

**Decision.** Rather than changing Phase 8's internal types (which would ripple through
persisted JSONB and the graph's own node contracts) or duplicating enrichment logic on
the frontend, `app/schemas/incident_api.py` defines response-only schemas, and
`_enrich_brief`/`_enrich_blast_radius` resolve Phase 8's ids into them at read time via
exactly two batched `IN` queries — never N+1, and a dangling reference (a citation
naming a chunk that's since been deleted, say) is dropped silently rather than raising,
since a partially-renderable brief is more useful than a 500. `_enrich_blast_radius`
specifically reuses Phase 4's own `BlastRadiusOut`/`BlastRadiusEntryOut` shape and
`catalog_service.get_services_by_ids` batch resolver — Phase 4 had already solved this
exact "ids in, resolved names/tiers out" problem for its own blast-radius endpoint, and
mirroring it beat inventing a second resolution path. Caught before any frontend code
was written by re-reading Phase 4's route first, not after F6 turned out to need data
the API didn't return.
