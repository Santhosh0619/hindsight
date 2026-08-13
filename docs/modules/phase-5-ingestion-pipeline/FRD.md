# FRD: Ingestion Pipeline & Job Queue

## API Endpoints (Backend — FastAPI)

All routes mounted under `/api/v1/workspaces/{workspace_id}/postmortems`. Auth:
`get_current_workspace` (any member) for reads; `require_role(OWNER, RESPONDER)` for
writes — same shape as Phase 4's catalog router.

### `POST /postmortems`
- Auth: owner/responder
- Request: `PostmortemCreate{title, raw_text, external_ref?, occurred_at?,
  duration_minutes?, severity?}`. `raw_text` capped at `settings.max_upload_bytes`
  (10 MiB) measured as UTF-8 byte length, not character count.
- Response `201`: `PostmortemOut` (`status="pending"`)
- Side effect: enqueues one `jobs` row, `kind="ingest_postmortem"`,
  `payload={"postmortem_id": "<uuid>"}`.
- Errors: `422` (raw_text exceeds the size cap, or is empty)

### `POST /postmortems/bulk`
- Auth: owner/responder
- Request: `PostmortemBulkCreate{items: list[PostmortemCreate]}`, `1 <= len(items) <=
  20`
- Response `201`: `list[PostmortemOut]`, one job enqueued per item
- Errors: `422` (empty list, over 20 items, or any item fails its own validation —
  the whole batch is rejected before any row is created, so a bad item can't leave a
  partial batch of postmortems created without a matching job)

### `GET /postmortems`
- Query: `status?` (filter), `cursor?`, `limit?` (default 20, max 100)
- Response `200`: `CursorPage[PostmortemOut]`

### `GET /postmortems/{id}`
- Response `200`: `PostmortemDetailOut{..., chunks: list[PostmortemChunkOut]}`
- Errors: `404`

### `GET /postmortems/{id}/status`
- Response `200`: `PostmortemStatusOut{status, injection_flagged, failure_reason}` — a
  deliberately small payload for a client polling ingestion progress every second or
  two without re-fetching chunk content on every poll.
- Errors: `404`

### `DELETE /postmortems/{id}`
- Auth: owner/responder
- Response: `204`. Cascades to `postmortem_chunks` via the existing FK
  `ondelete="CASCADE"` — no application-level chunk cleanup needed.
- Errors: `404`

All error responses use the existing `{"error": {"code","message","detail"}}` envelope.

## React Components (Frontend)

None — this phase is backend-only per Master-Prompt.md's phase breakdown. Any
ingestion UI is a later phase's concern.

## Data Model Changes

None — `postmortems`, `postmortem_chunks`, `jobs` already exist from Phase 1's initial
migration, matching plan.md §8 exactly (verified against `backend/app/models/
{postmortem,job}.py`), including the HNSW index on `postmortem_chunks.embedding`, the
GIN index on `postmortem_chunks.tsv`, the composite `(workspace_id, status)` index on
`postmortems`, and the partial index on `jobs(status, run_after)` scoped to
`status='queued'`. This phase adds no new tables or columns.

## Internal Architecture

### `app/workers/queue.py` — the job queue

```python
async def enqueue(
    db: AsyncSession, *, workspace_id: UUID, kind: str, payload: dict[str, object],
    run_after: datetime | None = None,
) -> Job: ...

async def claim(db: AsyncSession, *, worker_id: str, kinds: list[str], limit: int) -> list[Job]: ...

async def complete(db: AsyncSession, *, job: Job) -> None: ...

async def fail(db: AsyncSession, *, job: Job, error: str) -> None: ...

async def reclaim_expired(db: AsyncSession, *, lease_seconds: int) -> int: ...
```

`claim` is one atomic `UPDATE ... WHERE id IN (SELECT id FROM jobs WHERE
status='queued' AND run_after <= now() AND kind = ANY(:kinds) ORDER BY created_at FOR
UPDATE SKIP LOCKED LIMIT :limit) RETURNING *`, executed via `text()` — `SKIP LOCKED`
means two workers calling `claim` concurrently never both claim the same row, without
any application-level locking. Sets `status='running'`, `locked_by=:worker_id`,
`locked_at=now()`.

`fail` increments `attempts`; if `attempts >= max_attempts`, sets `status='dead'`;
otherwise sets `status='queued'`, `run_after = now() + backoff(attempts)` (exponential:
`min(2**attempts, 300)` seconds), and records `last_error`.

`reclaim_expired` finds `status='running' AND locked_at < now() - lease_seconds`
(a worker that claimed a job and then crashed before calling `complete`/`fail`) and
routes each through the same retry/dead-letter logic `fail` uses (incrementing
`attempts`) rather than silently requeuing forever — a job whose handler reliably
crashes the process (a poison payload) must still eventually reach `dead`, not retry
indefinitely just because it happens to crash the worker instead of raising cleanly.

### `app/workers/worker.py` — the poll loop

Async loop: `reclaim_expired` → `claim` a batch → dispatch each claimed job to its
handler (looked up by `kind` in a small registry dict) with bounded concurrency
(`asyncio.Semaphore`) → `complete` on success, `fail` on any exception, logging a
structured event per job (`job_id`, `kind`, `workspace_id`, `status`, `latency_ms`).
Sleeps briefly between cycles when nothing was claimed (avoids busy-polling the DB).
Installs a `SIGTERM` handler that stops claiming new jobs and waits (bounded) for
in-flight jobs to finish before exiting — a deploy/restart doesn't abandon a job
mid-run without a chance to complete.

### `app/workers/handlers/ingest_postmortem.py`

The `ingest_postmortem` job handler: loads the `Postmortem` row from
`payload["postmortem_id"]`, sets `status=processing`, runs `redact` → `screen` →
`chunk` → `embed` → `index` in sequence, sets `status=indexed` on success. Any
exception propagates to the worker's `fail()` call, which — separately from the job
retry itself — also sets the postmortem's own `status=failed` and `failure_reason` so
a reader doesn't see a postmortem stuck at `processing` forever while its job quietly
retries in the background.

### `app/services/ingestion/redact.py`

`redact(text: str) -> str` — a fixed, ordered list of compiled regexes masking: email
addresses, IPv4 addresses, `Authorization: Bearer <token>` / bare bearer-shaped
tokens, AWS-style access key IDs (`AKIA[0-9A-Z]{16}`), and connection-string-shaped
substrings (`scheme://user:pass@host`). Each match is replaced with a fixed placeholder
naming the category (e.g. `[REDACTED_EMAIL]`), not just asterisks — useful for a human
reviewing the redacted text to know *what* was removed without seeing the value.

### `app/services/ingestion/screen.py`

`screen(text: str) -> bool` — checks for a fixed list of instruction-like phrases
(case-insensitive: "ignore previous instructions", "ignore all previous", "disregard
the above", "you are now", "new instructions:"), zero-width Unicode characters
(`​`, `‌`, `‍`, `﻿`), and HTML comments (`<!--.*?-->`). Returns
`True` if anything matches. Pure detection — never modifies the text or blocks the
caller.

### `app/services/ingestion/chunk.py`

`chunk(text: str) -> list[ChunkSpan]` where `ChunkSpan{section_label: str | None,
content: str, char_start: int, char_end: int}`. First splits on lines matching a
postmortem section-heading pattern (`^#{1,6}\s+.+$` or `^(Summary|Timeline|Root
Cause(s)?|Impact|Action Items?|Detection|Remediation)s?:?\s*$`, case-insensitive);
text before the first recognized heading gets `section_label=None`. Any resulting
section longer than 1200 characters is further split at 1200-character windows with a
150-character overlap between consecutive windows, so a fact split across a chunk
boundary still appears whole in at least one chunk. `char_start`/`char_end` are offsets
into the original (redacted) text, so a citation can deep-link to the exact passage.

### `app/services/ingestion/embed.py`

`embed(texts: list[str]) -> list[list[float]]` — lazily loads
`SentenceTransformer(settings.embedding_model)` into a module-level singleton on first
call (one load per worker process, not per job), then `model.encode(texts,
batch_size=32)`, returning plain Python `list[float]` (384-dim, matching
`app.db.types.EMBEDDING_DIM`). Never imported by anything in `app/api/` — only the
ingestion handler (running in the worker process) calls it, per the NFR rule that LLM/
ML inference never runs in a request handler.

### `app/services/ingestion/index.py`

`index_postmortem(db: AsyncSession, *, postmortem: Postmortem, chunks:
list[ChunkSpan], embeddings: list[list[float]]) -> None` — deletes any pre-existing
chunks for the postmortem (re-ingestion safety), inserts one `PostmortemChunk` row per
chunk with `tsv` computed via `func.to_tsvector("english", content)` in the same
`INSERT`, and sets `postmortem.status = indexed`, all in one transaction/commit.

### `app/schemas/postmortem.py`

`PostmortemCreate`, `PostmortemOut`, `PostmortemDetailOut`, `PostmortemChunkOut`,
`PostmortemStatusOut`, `PostmortemBulkCreate` — the Pydantic v2 request/response models
listed under Endpoints.

### `app/api/v1/postmortems.py`

Thin FastAPI router matching the Endpoints section; auth via `get_current_workspace`/
`require_role`; delegates persistence to a `postmortem_service` module and enqueues via
`app.workers.queue.enqueue`.

## Dependencies

Depends on Phase 1's `Postmortem`/`PostmortemChunk`/`Job` models (unchanged) and Phase
2's `get_current_workspace`/`require_role` dependencies. Every later module that reads
postmortem content (extraction B8, retrieval B9-B10) depends on this phase's
`redacted_text`/chunks/embeddings existing and being correct — this phase is a hard
prerequisite for all of them.

## Sequence Flows

**Postmortem ingestion**
1. `POST /postmortems` → creates the `postmortems` row (`status=pending`) → enqueues
   an `ingest_postmortem` job → returns `201` immediately.
2. A worker's poll loop claims the job (`SKIP LOCKED`), sets `status=processing`.
3. Handler runs `redact` → `screen` → `chunk` → `embed` → `index` in sequence.
4. On success: `index_postmortem` sets `status=indexed` inside its own transaction;
   the worker calls `queue.complete`.
5. On any exception: the postmortem's `status` is set to `failed` with
   `failure_reason`; the worker calls `queue.fail`, which retries with backoff or
   dead-letters after `max_attempts`.

**Crashed worker**
1. A worker claims a job, crashes (process killed) before calling `complete`/`fail`.
2. The job sits `status=running` with a `locked_at` that stops advancing.
3. Any worker's next poll cycle calls `reclaim_expired`, which finds the stale lease
   (`locked_at` older than `lease_seconds`) and routes it through the same
   retry/dead-letter path as an explicit failure.

## Edge Cases & Error Handling

| Edge case | Handling |
|---|---|
| `raw_text` exceeds the size cap | `422`, rejected by `PostmortemCreate`'s validator before a row is ever created |
| Bulk request has 0 or >20 items | `422`, whole request rejected |
| Ingestion handler raises partway through (e.g. embedding fails) | Postmortem `status=failed` with `failure_reason`; job retried with backoff, no partial chunks ever committed (chunk insert is one transaction, only reached after embedding succeeds) |
| Two workers claim concurrently | `SKIP LOCKED` guarantees disjoint claims — never a double-processed job |
| Worker crashes mid-job | Reclaimed by lease expiry on the next poll cycle from any worker, retried with the same backoff/dead-letter path as a normal failure |
| Job exhausts `max_attempts` | `status=dead` — never retried again automatically; the postmortem stays `failed` for a human to investigate |
| Postmortem contains a secret-shaped string | Redacted before chunking/embedding/indexing; `raw_text` (unredacted) is never read by chunk/embed/index, only stored for the uploader's own reference |
| Postmortem contains an injection-shaped instruction | `injection_flagged=true`, ingestion proceeds normally — screening never blocks |
| `viewer` calls a write endpoint | `403`, via `require_role(OWNER, RESPONDER)` |
| Non-member queries any postmortem endpoint | `404`, via the existing `get_current_workspace` dependency |
| Postmortem deleted while its job is still queued/running | Handler's `db.get(Postmortem, id)` returns `None`; handler treats this as a no-op success (nothing to ingest, not a failure) rather than raising |
