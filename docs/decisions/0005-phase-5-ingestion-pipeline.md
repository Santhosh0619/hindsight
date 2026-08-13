# ADR 0005: Ingestion Pipeline & Job Queue — Design and Bugs Found

## 1. `reclaim_expired` routes through `fail()`, not a silent requeue

**Context.** Master-Prompt.md's Phase 5 spec says to "reclaim jobs whose lease expired
(crashed worker)" without specifying whether a reclaim counts as a retry attempt. The
naive option — just flip `status` back to `queued` and clear the lock — treats a crash
identically to nothing having happened.

**Decision.** `reclaim_expired` finds every `status='running'` job whose `locked_at` is
older than the configured lease (`Settings.job_lease_seconds`, default 120s) and routes
each one through the exact same `fail()` path an explicit handler exception uses —
incrementing `attempts` and dead-lettering once `max_attempts` is reached. A job whose
handler reliably crashes the worker process outright (a poison payload that segfaults
or OOMs the process, say) would otherwise never raise a catchable exception and would
sit in an infinite reclaim→run→crash→reclaim loop forever. Routing through `fail()`
guarantees every job reaches a terminal state (`done` or `dead`) regardless of *how* it
fails, matching the NFR's reliability requirement.

## 2. `claim()`'s post-UPDATE SELECT needs `populate_existing=True` — caught by tests, not review

**Context.** `claim()` runs the `SKIP LOCKED` `UPDATE ... RETURNING id` as raw SQL, then
does a normal `select(Job).where(Job.id.in_(claimed_ids))` to return typed ORM objects.
The first version of `test_queue.py` failed with claimed jobs reporting
`status=queued` instead of `status=running` — the UPDATE had genuinely committed
(confirmed by inspecting the row directly), but the Python object returned to the test
still showed the pre-claim value.

**Decision.** The cause is SQLAlchemy's identity map: this project's session factory
sets `expire_on_commit=False` (a deliberate Phase 1 choice, so already-loaded attributes
survive a commit without an extra round trip), which means a `select()` against a
session that already holds an object for a given primary key returns the *existing*
in-memory instance by default rather than overwriting it from the fresh query results.
Since `enqueue()` and `claim()` were called against the same session in the failing
test (an artificial-but-legitimate scenario — nothing stops a real caller from doing
this too), the returned `Job` was stale. Fixed by adding
`.execution_options(populate_existing=True)` to the post-UPDATE `SELECT`, which forces
SQLAlchemy to overwrite already-loaded attributes with the query's actual result rows
regardless of identity-map presence. Notable because every other query pattern in this
codebase (Phase 1-4) happened to never re-query an object it had just mutated via raw
SQL in the same session — this is the first place that combination occurs, and the
default ORM behavior there is a real, easy-to-miss trap.

## 3. Redaction pattern order: connection strings before email/IP

**Context.** A naive redaction pass over `postgres://svc_user:hunter2@db.internal:5432/
mydb` with an email pattern applied first partially matches `hunter2@db.internal` as if
it were an email address (the email regex doesn't care what precedes the `@`), leaving
the surrounding connection-string structure mangled and the credential only partially
obscured.

**Decision.** `redact.py`'s pattern list is deliberately ordered — connection strings
and bearer tokens are matched and replaced *before* the generic email/IP patterns run,
so a credential embedded in a connection string is redacted as one unit
(`[REDACTED_CONNECTION_STRING]`) rather than being picked apart by a later, more
generic pattern. Order is load-bearing here, not incidental — documented inline in
`redact.py` so a future added pattern doesn't get inserted in the wrong position.

## 4. `embed()` runs `model.encode` in a thread, not inline on the event loop

**Context.** `sentence-transformers`' `.encode()` is a synchronous, CPU-bound call.
Calling it directly inside an `async def` blocks the worker's entire event loop for the
duration of the encode — with `Worker`'s bounded concurrency (`asyncio.Semaphore`)
meant to let several jobs progress concurrently, a blocking encode would defeat that
entirely (every other claimed job's DB I/O would also stall until the encode returns).

**Decision.** `embed()` wraps both the model's lazy first-load and every `.encode()`
call in `asyncio.to_thread(...)`, moving the blocking work off the event loop thread.
The model itself is a lazy-loaded module-level singleton guarded by an `asyncio.Lock`
(so two jobs racing to embed their first batch don't trigger two redundant model
loads) — loaded once per worker process, not once per job, since a cold load takes
seconds and a job takes milliseconds once the model is warm.

## 5. Verified end-to-end against the live worker container, not just pytest

**Context.** Every prior phase's ADRs note that some bug classes only show up against
real infrastructure (a live Postgres, a real browser, actual HTTP cookie semantics).
This phase's worker process is exactly that kind of surface — pytest's simulated
`_run_pending_ingestion_jobs` helper (drives the handler directly, since the real
`worker` container isn't running during a `pytest` invocation) proves the pipeline
logic is correct, but doesn't prove the actual `docker-compose.yml` `worker` service
boots, connects, and processes a real queued job end to end.

**Decision.** Before considering this phase done, started the real `worker` container
and drove it via `curl` against the live `api` container: signed up, created a
postmortem containing a planted AWS access key, a planted email, and an injection
phrase, and polled `/status` until it reached `indexed`. Confirmed via `GET
/postmortems/{id}` that the stored chunk content had both secrets redacted
(`[REDACTED_EMAIL]`, `[REDACTED_AWS_KEY]`) and `injection_flagged=true`, and confirmed
via `docker compose logs worker` that the structured `postmortem_ingested`/
`job_completed` events fired with the expected fields. This is the check that would
have caught a docker-compose wiring bug (wrong `DATABASE_URL`, a missing volume mount
for the model cache, an import error only triggered by the `python -m
app.workers.worker` entrypoint and not by `pytest`) that unit/integration tests alone
cannot see, since they never actually exercise that entrypoint.

## 6. Test isolation: a unique job `kind` per `test_queue.py` test

**Context.** The dev Postgres container persists data across separate manual `pytest`
invocations within a single work session (there's no per-run truncation, unlike the
isolated `docker-compose.test.yml` stack Phase 3 built for e2e). Early versions of
`test_queue.py` asserted exact claimed-job counts and exact returned-job-list equality;
after several repeated manual test runs while debugging the `populate_existing` bug
above, these assertions started failing — not because of a real regression, but because
leftover `queued`/`running` rows from earlier debug runs (using the same `kind="test
_job"` string) were still sitting in the shared database and getting swept up by a
later test's `claim()`/`reclaim_expired()` calls.

**Decision.** Every `test_queue.py` test now generates its own unique `kind` string
(`test-kind-<random>`) via a shared helper, so `claim()`-based assertions (which filter
by `kind`) are fully immune to cross-run leftovers regardless of how many times the
suite has been run against the same un-truncated dev database. `reclaim_expired()` is
deliberately global across kinds (see §1 — a worker pool reclaims stale leases for
every tenant and job kind, not just one), so its two tests assert the *specific* job of
interest reached the expected state rather than asserting an exact aggregate count,
which a shared table genuinely cannot guarantee in isolation. CI's fresh-database-per-
run isolation means this class of flakiness would never surface there — this was purely
a consequence of iterating locally against a long-lived dev container — but the fix
makes the tests correct as a general isolation property, not just a workaround for this
one session.

## 7. Code review found two observability gaps, no correctness bugs

**Context.** The NFR's Observability section explicitly lists `job_claimed` alongside
`job_completed`/`job_failed`/`job_dead_lettered` as the four job-lifecycle events, and
lists `duration_ms` alongside `chunk_count`/`injection_flagged` as fields on
`postmortem_ingested`. The first implementation logged three of the four lifecycle
events (claim itself was silent) and omitted `duration_ms`.

**Decision.** Added the missing `job_claimed` event (in `Worker.run()`, right after a
non-empty claim) and `duration_ms` (timed from the start of
`handle_ingest_postmortem`, mirroring the pattern `worker.py` already used for
`job_completed`). Both are one-line additions with no behavioral change — caught
because the NFR spelled out the exact field/event list rather than saying "add
logging," which gave the reviewer something concrete to check the code against.
