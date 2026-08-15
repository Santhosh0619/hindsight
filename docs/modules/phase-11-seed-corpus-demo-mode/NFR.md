# NFR: Seed Corpus & Demo Mode

## Performance

- `make seed` must complete in under 5 minutes with no LLM key configured (PRD
  acceptance criterion). The only genuinely slow step is embedding 80 postmortems'
  worth of chunks locally via `sentence-transformers` — everything else (catalog
  import, direct fact/service/failure-mode inserts, retrieval/blast-radius calls for
  8 precomputed briefs) is small, in-process Postgres work. Embeddings are batched
  per postmortem (`embed([span.content for span in spans])`), matching the existing
  ingestion handler's own batching, not embedded one chunk at a time.
- Generator scripts (`generate_*.py`) run once, at author time, not as part of `make
  seed` — their own runtime cost is irrelevant to the 5-minute budget, since their
  output is what's actually committed and loaded.

## Security

- The demo guest's expanded permission (Gap #5) is scoped to exactly three endpoints
  (`POST /incidents`, `POST .../brief`, `GET .../brief/stream`) via a dedicated
  dependency, not a role change — every other write path a real viewer can't reach
  stays exactly as unreachable for a demo guest.
- `demo_brief_bucket` bounds the compute (and, once a key exists, LLM spend) a single
  demo guest session can trigger, independent of the per-IP `demo_signup_bucket` that
  already bounds how many guests one IP can mint.
- Demo guest accounts are unchanged from Phase 2: a random-password argon2 hash with
  no known plaintext, `is_demo=True`, never intended to be logged into directly.
- The seed corpus is entirely synthetic and labeled as such (PRD) — no real incident,
  postmortem, or service data from any actual system is ever included.

## Reliability

- `make seed` is idempotent (FR-06) — safe to run again after a partial failure or a
  redeploy without producing duplicate rows or erroring on rows that already exist.
- A demo guest's rate-limited brief request fails the same documented way any other
  rate-limited request does (`RateLimitedError`, existing error shape) — never a
  silent hang or a different, undocumented failure mode.
- Precomputed briefs are real `Brief` rows going through the exact same
  `_enrich_brief` read path Phase 9 built — nothing about how they're read differs
  from a genuinely live-generated brief; the only difference is `llm_used=false`,
  `from_cache=true`, and how they were written.

## Observability

- `seed.py` logs a `structlog` summary per section (`catalog_seeded`,
  `postmortems_seeded`, `incidents_seeded`, `briefs_precomputed`, `eval_cases_
  seeded`) with counts and duration, so `make seed`'s progress and the 5-minute
  budget are both directly observable from its own output, not inferred.
- `demo_brief_bucket` rejections log the same way `demo_signup_bucket`'s already do.

## Testability

- Backend: `test_seed.py` runs `seed.py`'s loader against a real (test) database and
  asserts the documented counts (40 services, 8 teams, 80 postmortems, 12 incidents,
  8 briefs, 20 eval cases), that every fact's `source_chunk_id` resolves to a real
  chunk whose `section_label` matches the fact's type, that the 2 deliberate SPOFs
  in the catalog genuinely have no redundant path, and that running the loader twice
  produces the same counts the second time (idempotency, FR-06) — not just that it
  doesn't raise. `test_demo_mode.py` covers `require_role_or_demo` (a demo guest
  passes, a real viewer doesn't, an owner does) and `demo_brief_bucket` exhaustion.
- Frontend: a component test for `DemoBanner` (renders for `is_demo`, absent
  otherwise) and for the `useCanGenerateBrief` gate on `NewIncident`/`IncidentDetail`
  (a demo guest sees the write affordance a plain viewer doesn't).
- E2E: the existing "Try the live demo" test (`auth-frontend.spec.ts`, since Phase 3)
  already covers the login path itself. This phase adds a real end-to-end pass
  against the *seeded* corpus specifically: log in as a demo guest, browse a
  populated Knowledge Base/Service Map/Dashboard (not an empty-state), open one of
  the 8 precomputed-brief incidents and see real hypotheses/citations render, and —
  the actual signature demo moment — paste a new alert as the demo guest and watch a
  brand-new brief generate against the real seeded corpus.

## Constraints

- Everything from Phases 1-10's NFRs still applies (async throughout, Pydantic v2 at
  every boundary, `mypy --strict` clean, `workspace_id` filtering on every
  tenant-scoped query, TypeScript strict, React Query for server state).
- No new database tables or migrations (see FRD "Data Model Changes").
- No new backend or frontend dependencies — catalog import, ingestion, retrieval,
  and correlation all reuse existing Phase 4/5/8 functions directly; the demo banner
  and rate limiter reuse existing UI primitives and the existing `TokenBucket` class.
- The generator scripts (`generate_*.py`) are deterministic given a fixed seed
  (`random.Random(<fixed int>)`, never the module-global `random` state) so
  regenerating fixtures from scratch reproduces byte-identical output — required by
  FR-01 and by "commit the output as JSON fixtures" actually meaning something.
