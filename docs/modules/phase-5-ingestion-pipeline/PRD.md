# PRD: Ingestion Pipeline & Job Queue
Phase: 5
Module codes: B7 (`ingestion`), B13 (`jobs`) from plan.md §6

## Problem

Every later feature — extraction (Phase 6), hybrid retrieval (Phase 7), incident briefs
(Phase 8-9) — depends on postmortems existing in the system as searchable, embedded
text. A postmortem arrives as free-form pasted text from a human, which means it can
contain secrets that must never reach an LLM or a search index, and can contain
adversarial instruction-like content aimed at whatever model reads it later. None of
the downstream work in this project can start until there's a safe, reliable pipeline
that takes raw text in and produces redacted, chunked, embedded, indexed rows out — and
since embedding a large postmortem is too slow to do inline in a request handler, that
pipeline needs to run in the background behind a durable job queue, not inline.

## Actors

- A workspace owner/responder, pasting or bulk-uploading postmortems.
- A `viewer`, who can read postmortems and their processing status but not add or
  remove them.
- The background worker process, which claims and executes ingestion jobs.
- Every later backend module that reads `postmortem_chunks`/`postmortems` (retrieval in
  Phase 7, extraction in Phase 6) — this phase is what populates those tables in the
  first place.

## Functional Requirements

FR-01: `POST /postmortems` accepts a title and raw text (plus optional metadata:
`external_ref`, `occurred_at`, `duration_minutes`, `severity`), creates a `postmortems`
row with `status=pending`, and enqueues one `ingest_postmortem` job. The response
returns immediately with the created row (still `pending`) — ingestion happens
asynchronously.

FR-02: `POST /postmortems/bulk` accepts a list of the same payload (capped at 20 items
per call) and does the same for each — one row and one job per item, not a single
combined job, so one bad postmortem in a batch doesn't block the others.

FR-03: The ingestion job, once claimed by the worker, runs redaction → injection
screening → chunking → embedding → indexing in sequence, updating `status` to
`processing` when it starts and `indexed` when all steps succeed, or `failed` (with
`failure_reason`) if any step raises.

FR-04: Redaction produces `redacted_text` from `raw_text` by masking emails, IP
addresses, bearer tokens, AWS-style access keys, database connection strings, and other
high-entropy secret-shaped substrings. `raw_text` is retained (for audit/display to the
uploader), but every downstream consumer — chunking, embedding, and every later phase's
LLM calls — reads `redacted_text` only, never `raw_text`.

FR-05: Injection screening inspects the text for instruction-like content aimed at a
future LLM reader (phrases like "ignore previous instructions", zero-width characters,
HTML comments hiding text) and sets `injection_flagged` accordingly. Screening never
blocks ingestion — a flagged postmortem still gets chunked, embedded, and indexed; the
flag is surfaced to the caller so a human (or a later phase's UI) can review it.

FR-06: Chunking is section-aware: postmortems have structure (Summary, Timeline, Root
Cause, Impact, Action Items), so chunking splits on recognizable section headings
first, then size-splits any section still longer than ~1200 characters with a 150
character overlap between consecutive chunks. Each chunk records `section_label`,
`char_start`, and `char_end` so a later citation can deep-link to the exact source
passage.

FR-07: Embedding uses a local `sentence-transformers` model (no external API, no key
required) to produce a 384-dimension vector per chunk, batched across a postmortem's
chunks in one call. The model loads once per worker process, not once per job.

FR-08: Indexing writes all of a postmortem's chunks (content, section metadata,
embedding, and a `tsvector` for keyword search) in a single transaction, then flips the
postmortem's status to `indexed` — a reader never observes a postmortem in a
partially-indexed state.

FR-09: The job queue (`jobs` table) supports safe concurrent claiming by multiple
worker processes (`FOR UPDATE SKIP LOCKED`), exponential-backoff retry on failure up to
`max_attempts`, dead-lettering after that, and reclaiming jobs whose worker crashed
mid-run (a lease that's expired without completion or an explicit failure).

FR-10: `GET /postmortems` lists a workspace's postmortems (cursor-paginated, filterable
by `status`); `GET /postmortems/{id}` returns one postmortem plus its chunks;
`GET /postmortems/{id}/status` is a lightweight poll endpoint returning just
`status`/`injection_flagged`/`failure_reason`, for a client polling ingestion progress
without pulling the full chunk set on every poll. `DELETE /postmortems/{id}` removes a
postmortem and its chunks (cascade).

FR-11: Only `owner`/`responder` can create, bulk-create, or delete postmortems; any
workspace member can read them — the same RBAC shape Phase 4 established for the
catalog.

## User Stories

- As a responder who just resolved an incident, I want to paste the postmortem I wrote
  and have it become searchable within seconds, without worrying that a stray AWS key
  in a log excerpt leaks into an embedding index or an LLM prompt.
- As a workspace owner bootstrapping a new workspace, I want to bulk-upload a batch of
  historical postmortems in one call instead of one-by-one.
- As a `viewer`, I want to see what's been ingested and its status without being able
  to add or delete anything.
- As the author of a later module (extraction, retrieval), I want every postmortem
  chunk to already be redacted, embedded, and indexed by the time my code ever sees it
  — ingestion correctness is not something later phases should have to re-verify.

## Out of Scope

- Fact/failure-mode/service-link extraction from postmortem content — Phase 6.
- Hybrid retrieval that actually searches these chunks — Phase 7.
- A file-upload UI or drag-and-drop — this phase is backend-only; Phase 10 (or later)
  owns any frontend for ingestion. The API accepts pasted/bulk JSON text, not a
  multipart file upload, this phase.
- CSV/PDF parsing of postmortem source documents — plain text in, this phase.

## Acceptance Criteria

1. Paste a postmortem via `POST /postmortems`: the response returns immediately with
   `status=pending`; polling `GET /postmortems/{id}/status` shows it move to
   `processing` then `indexed` within a few seconds; the postmortem's chunks exist with
   384-dimension embeddings and non-null `tsv`.
2. A postmortem containing a planted fake AWS access key and a fake bearer token does
   not have either string appear anywhere in `redacted_text` or in any chunk's
   `content`.
3. A postmortem containing an injected instruction phrase ("ignore all previous
   instructions...") is still fully ingested (`status=indexed`) with
   `injection_flagged=true`, not blocked or failed.
4. Two worker processes claiming from the same queue concurrently never both claim the
   same job; a job whose handler raises retries with backoff up to `max_attempts`, then
   moves to `dead`; a job whose worker is killed mid-run (lease expires) gets reclaimed
   and retried by another worker.
5. A `viewer` gets `403` on `POST`/`POST /bulk`/`DELETE`; every endpoint is
   `workspace_id`-scoped (a member of workspace A gets `404` on workspace B's
   postmortems).
6. `ruff`, `mypy --strict`, and `pytest` are all clean.
