# NFR: Extraction Agents (Pydantic AI)

## Performance

- All three extraction agents run inside one `extract_postmortem` job, not three
  separate queued units — avoids three independent claim/backoff/retry timelines for
  what's conceptually one unit of work per postmortem, and avoids three times the
  queue-claim overhead.
- The router retries within a provider before falling through to the next one — bounded
  by `tenacity`'s configured attempt count, not unbounded, so a genuinely-down provider
  fails over in a fixed number of attempts rather than hanging the job.

## Security

- Every extraction-triggered DB write (`PostmortemFact`, `PostmortemFailureMode`,
  `PostmortemService`) is scoped to the postmortem's own `workspace_id` — service-name
  resolution explicitly queries `catalog_service.list_services(db, workspace_id)`
  scoped to the postmortem's workspace, so a postmortem in workspace A can never link
  to a service that exists only in workspace B, even if the model hallucinates a name
  that happens to match one there.
- Every prompt sent to an LLM explicitly delimits postmortem chunk content and states
  it is untrusted data, per FR-08 — the same discipline Phase 5's `screen.py` exists to
  flag, now enforced at the point the content actually reaches a model, not just
  detected at ingest time.
- No API key is ever logged, including in `jobs.last_error` on an
  `LLMUnavailableError` — provider construction reads keys from `Settings` and never
  includes them in any exception message or structured log field.

## Reliability

- `extract_postmortem` failures (including "no LLM configured") go through the exact
  same retry/backoff/dead-letter machinery Phase 5 built for every other job kind — no
  extraction-specific special-casing, so this phase adds zero new failure-handling
  surface area to reason about.
- Extraction never marks a postmortem's own `status` (from ingestion) as failed —
  ingestion and extraction are independent lifecycles; a postmortem can be
  `status=indexed` with a permanently-dead-lettered extraction job if no LLM is ever
  configured, and that's the correct, honest state, not a bug to hide.
- The hallucination guard (dropping facts citing unknown `chunk_id`s, dropping
  unresolved service names) is deterministic Python code, not a second LLM call
  asking the model to "double check itself" — verifiable and testable independent of
  any model's actual behavior.

## Observability

- `structlog` events for the extraction job's outcome (`postmortem_extracted` on
  success with `fact_count`/`failure_mode_count`/`service_link_count`/`duration_ms`,
  matching Phase 5's `postmortem_ingested` event shape), and the existing
  `job_completed`/`job_failed`/`job_dead_lettered` events already cover the job-queue
  layer without any extraction-specific duplication.

## Testability

- No real LLM key is configured for this build session (plan.md §10's "no key at all"
  degradation level, and Santhosh's explicit choice this phase: build and verify
  against mocks, add a real key and verify live generation himself later). Every agent
  and router test uses `pydantic-ai`'s `TestModel`/`FunctionModel` — these exercise the
  exact same `Agent(model, output_type=...)`/`.output` code path a real Gemini/Groq/
  Ollama call would, verified directly against the installed `pydantic-ai` 2.29.0 (not
  assumed), so agent-construction bugs are still caught even without hitting a real
  API.
- `test_llm_router.py` covers: primary-provider success, fallback to a second provider
  after the first raises, and `LLMUnavailableError` when every provider fails —
  using fake `LLMProvider` implementations, not real network calls.
- `test_extraction.py` covers each agent's typed output shape via `TestModel`
  (auto-generates schema-valid dummy data) and, for the injection/hallucination-guard
  cases specifically, a `FunctionModel` with a custom function that lets the test
  assert on exactly what prompt text the agent actually sent — proving injected
  content was delimited as data, not that the model merely "behaved" (which a
  `TestModel`-only test can't distinguish from coincidence).
- `test_extraction_service.py` covers the deterministic guards end-to-end: a fact
  citing a fake `chunk_id` is dropped, a service name not in the catalog is dropped, a
  workspace-scoped `FailureMode` row is get-or-created correctly.
- All tests run against a real Postgres for persistence (same pattern as every prior
  phase) — only the LLM call itself is faked, not the database layer.

## Constraints

- Everything from Phases 1-5's NFRs still applies (async throughout, Pydantic v2 at
  every boundary, typed exceptions, `mypy --strict` clean, no bare dicts,
  `workspace_id` filtering on every tenant-scoped query, no blocking calls in an async
  context).
- No new database tables/migrations — this phase builds entirely on Phase 1's existing
  `postmortem_facts`/`postmortem_services`/`postmortem_failure_modes`/`failure_modes`/
  `semantic_cache` schema.
- LLM calls only from the worker (job handler), never from a request handler — same
  rule Phase 5 established for embedding, extended here to every LLM call this phase
  introduces.
- `groq` added as an explicit new backend dependency (`pydantic-ai`'s bundled extras
  include Google support by default but not Groq — confirmed via the installed
  package's own import error, not assumed) — the only new dependency this phase adds.
