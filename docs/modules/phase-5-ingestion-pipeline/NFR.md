# NFR: Ingestion Pipeline & Job Queue

## Performance

- Embedding runs in the worker process, batched per postmortem (one `model.encode`
  call across all of a postmortem's chunks), not one call per chunk — MiniLM on CPU is
  fast enough at this project's scale (plan.md §10/§15) as long as it's never called
  per-chunk in a loop.
- The `SentenceTransformer` model loads once per worker process (module-level
  singleton, lazy first-call), not once per job — a cold model load is seconds; paying
  that on every job would make ingestion visibly slow.
- `jobs(status, run_after)` is a partial index scoped to `status='queued'` (already in
  place from Phase 1's migration) so the claim query stays cheap as the table
  accumulates `done`/`dead` rows over the life of a workspace.
- The claim query (`SKIP LOCKED`) and the chunk-insert transaction are each a single
  round trip — no per-chunk queries in the hot ingestion path.

## Security

- `redacted_text` — never `raw_text` — is the only thing chunking, embedding, and
  every later phase's LLM calls ever read. `raw_text` is retained solely for the
  uploader's own reference (e.g. a "view original" affordance some later UI might add)
  and is never passed to an embedding model or an LLM.
- Every postmortem/job query is `workspace_id`-scoped at the service-layer function
  boundary, matching Phase 4's established discipline — not left to the route to
  remember.
- Read access requires only workspace membership; create/bulk-create/delete require
  `owner` or `responder` via the existing `require_role` dependency — no new RBAC
  mechanism introduced.
- Injection screening is detection-only (`injection_flagged`), never a block — Phase
  6+'s agent prompts are responsible for treating retrieved postmortem content as
  untrusted data regardless of this flag; the flag is a signal for a human/UI, not a
  security boundary by itself.

## Reliability

- The job queue is durable (a Postgres table, not an in-memory queue) — a worker
  restart or redeploy never loses a queued or in-flight job; `reclaim_expired` recovers
  jobs whose worker crashed without an explicit failure.
- Every job kind reaches a terminal state eventually: `done`, or `dead` after
  `max_attempts` — no job retries forever, including one whose handler crashes the
  process outright (reclaim increments `attempts` the same as an explicit `fail`).
- Chunk indexing is one transaction — a postmortem is never observably
  partially-indexed (some chunks present, others missing) to a concurrent reader.
- A postmortem whose job dead-letters is left `status=failed` with a `failure_reason`,
  not silently stuck at `pending`/`processing` forever — always inspectable by a human.

## Observability

- `structlog` events per job lifecycle transition (`job_claimed`, `job_completed`,
  `job_failed`, `job_dead_lettered`) at `info` level (or `warning` for
  `job_dead_lettered`), each carrying `job_id`, `kind`, `workspace_id`, and — for
  failures — `error`, matching the structured-logging pattern established since Phase
  1.
- Ingestion pipeline steps log their own `postmortem_ingested` event (with
  `chunk_count`, `injection_flagged`, `duration_ms`) on success, so ingestion
  throughput/latency is visible without instrumenting every step separately.

## Testability

- Backend: `test_queue.py` covers claim/complete/fail/backoff/dead-letter, concurrent
  claiming via `SKIP LOCKED` (two claims never return overlapping job sets), and lease
  reclaim for a job stuck `running` past its lease. `test_ingestion.py` covers
  redaction (planted secrets of every category never survive into `redacted_text`),
  injection screening (flagged vs. clean text), chunking (section-boundary splitting,
  long-section size-splitting with overlap, `char_start`/`char_end` correctness), and
  embedding output shape (384-dim vectors). `test_postmortems.py` covers the API: CRUD,
  RBAC, cross-tenant 404, bulk cap enforcement, and end-to-end ingestion (paste →
  poll status → `indexed`, chunks present with embeddings).
- All tests run against a real Postgres (same pattern as Phase 2 and 4 —
  `SKIP LOCKED` concurrency and `to_tsvector`/HNSW behavior can't be meaningfully
  verified against a mock) and the real `sentence-transformers` model (no mocked
  embeddings — the model is small enough to run in CI within the existing time
  budget).

## Constraints

- Everything from Phases 1-4's NFRs still applies (async throughout, Pydantic v2 at
  every boundary, typed exceptions, `mypy --strict` clean, no bare dicts,
  `workspace_id` filtering on every tenant-scoped query).
- No new database tables/migrations — this phase builds entirely on Phase 1's existing
  `postmortems`/`postmortem_chunks`/`jobs` schema.
- No Redis, no Celery, no dedicated queue broker — a Postgres-backed queue only, per
  plan.md §7/§10's explicit one-database, zero-paid-infra rationale.
- Embedding is local (`sentence-transformers`, no API key) — ingestion must fully
  function with `llm_api_key` unset, since it never calls an LLM at all this phase.
