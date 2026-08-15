# NFR: Observability, Settings, API Keys

## Performance

- `GET .../agent-runs`/`.../audit-log` are cursor-paginated, same indexed
  `(workspace_id, created_at)`-shape queries every other list endpoint in this
  codebase already uses — no new index needed (`agent_runs` joins through
  `incidents.workspace_id`, already indexed; `audit_log.workspace_id` already indexed
  from Phase 1).
- `GET .../agent-runs/stats` aggregates with `SUM`/`COUNT` at the database, never by
  loading every run into Python — same discipline as Phase 10's dashboard aggregates.
- The LLM connection test makes at most 3 real network calls (one per provider slot),
  sequentially is fine — it's an explicit owner-initiated diagnostic action, not
  something on any page-load path, so there's no latency budget forcing concurrency
  the way a request-path call would need.
- `POST /ingest/postmortem` has the exact same latency profile as the existing
  session-authenticated create route, since it calls the identical service function —
  no new performance surface to characterize.

## Security

- Auth enforcement points: `CurrentWorkspaceMember` (read endpoints, any role) and
  `require_role(OWNER)` (every write in Settings, API key CRUD, the LLM test) via
  FastAPI dependencies, never a manual `if` inside a handler — matching every prior
  phase's pattern.
- API keys are hashed with SHA-256, not argon2 — see FRD "Internal Architecture"
  `apikey_service` for the full reasoning (256 bits of real entropy from
  `secrets.token_urlsafe`, not a human-chosen low-entropy password; the access path is
  a high-frequency hash lookup on every webhook call, which argon2's deliberate
  slowness would directly hurt with no offsetting security benefit here). This is a
  deliberate departure from `hash_password`'s argon2id, not an oversight — the two
  hash different threat models.
- The raw key is returned exactly once, at creation, and never again — `ApiKeyOut` (the
  shape every other read uses) has no field capable of carrying it, not even truncated
  or masked; only `ApiKeyCreatedOut` (the create response's own distinct schema) does.
  Never logged: `apikey_service.create_key`'s structlog event carries `key_id`/`prefix`,
  never `raw_key`.
- `X-API-Key` is a plain header value, not a bearer-token/cookie hybrid — no CSRF
  concern (a webhook caller is a script, not a browser with ambient cookies) and no
  session-fixation surface, since it authenticates a workspace, never a user, and
  underlies exactly one route (`POST /ingest/postmortem`), not the whole API surface a
  leaked user session would expose.
- `GET .../apikeys` is OWNER-only (not "any role" like the other Settings-adjacent
  reads) — seeing which key names/prefixes exist is itself a piece of information
  about the workspace's external integrations that a viewer/responder has no
  legitimate need for, distinct from members/audit-log which are ordinary operational
  visibility.
- Workspace deletion's typed-confirmation gate is a UX safeguard against misclicks,
  not a security boundary — the actual authorization boundary is `require_role(OWNER)`
  on the existing `DELETE /workspaces/{id}`, already enforced since Phase 2.
- No secret, key, or model id hardcoded anywhere in this diff — the LLM test endpoint
  reads the same `Settings` fields the router already does, never a literal value.

## Reliability

- A failed LLM connection test degrades to a reported failure in the response body
  (`ok: false`), never a 500 or an unhandled exception — the endpoint's entire job is
  to surface exactly that failure to an operator, so raising it instead would defeat
  the feature.
- `structured_with_usage`'s addition to `LLMProvider` is purely additive — every
  existing caller of `.structured()` (Phase 6 extraction agents, Phase 12's
  groundedness judge) is untouched, so this phase carries zero regression risk to
  already-shipped LLM call sites.
- The ingest webhook shares `create_postmortem`'s existing degradation behavior
  exactly (size cap, redaction, injection screening, queue-backed async processing) —
  nothing new to characterize since nothing new was built there.

## Observability

- New structlog events: `agent_run_stats_computed` is deliberately *not* logged (a
  read endpoint, not a state change — matches the "reads don't get their own
  lifecycle event" precedent from every prior list endpoint in this codebase).
  `api_key_created`/`api_key_revoked` (key_id, prefix, actor_user_id — never
  `raw_key`), `llm_provider_tested` (provider, configured, ok, latency_ms — one event
  per slot tested), `postmortem_ingested_via_api_key` is **not** a separate event —
  `postmortem_created`/`postmortem_ingested` (Phase 5) already fire unconditionally
  inside `create_postmortem`/the worker handler regardless of which auth path called
  them, so no duplicate logging path is needed; the workspace_id in those existing
  events is sufficient to know an API-key-originated postmortem from a session one
  only needs `created_by is None` as the distinguishing signal, already available on
  the row.
- Every owner-only write in this module writes an `audit_log` row via the existing
  `write_audit_log` helper — `api_key.created`, `api_key.revoked`,
  `workspace.llm_test_run` is explicitly **not** audit-logged (a read/diagnostic
  action, not a mutation — matches `audit_log`'s existing scope of "things that
  changed state," not "things that were viewed").

## Testability

- Backend: unit tests for `apikey_service` (hash/prefix generation, authenticate
  success/unknown/revoked), integration tests against the real dev Postgres for the
  full CRUD + the ingest webhook's happy path and 401 paths (mirrors
  `test_evaluation_runner.py`'s real-ingestion-pipeline precedent from Phase 12 — no
  mocking the queue/worker). `structured_with_usage` tested via `pydantic-ai`'s real
  `TestModel` (Phase 6/8/12 precedent), asserting the returned `LLMResponse.tokens_in/
  out` are nonzero and that the existing `.structured()` callers are provably
  unaffected (their own existing test suites staying green is the proof).
- Frontend: component tests for `RunStatsCards`/`RunsTable`/`RunWaterfall`/
  `MembersPanel`/`ApiKeysPanel`/`LlmProviderPanel`/`DangerZonePanel`, each asserting
  its own loading/error/empty states and (for the owner-only panels) that a
  non-owner's write controls are absent, not just disabled.
- E2E: the literal Master-Prompt.md checkpoint (create key → POST via webhook → watch
  it ingest → revoke → confirm 401) as one journey; separately, a Settings walkthrough
  (invite, change role, create+revoke an API key) and confirmation that a
  viewer/responder session never sees Settings' write controls (extends
  `rbac-shell.spec.ts`'s existing pattern, not a new file, since it's the same
  "viewer sees no write entry points" assertion this repo already has one file for).

## Constraints

- No LLM call in a request handler — the one exception this phase adds,
  `POST .../settings/llm/test`, is a deliberate, explicit, owner-initiated diagnostic
  action calling `.complete()` directly (not through a background job), which
  CLAUDE.md's rule exists to prevent for *implicit*, request-path LLM usage (e.g. brief
  generation, correctly kept in a background-adjacent SSE-streamed flow since Phase 9)
  — a synchronous "test my own configuration" button calling the provider directly,
  with the user staring at a spinner waiting specifically for that network call, is the
  one legitimate case CLAUDE.md's own reasoning doesn't forbid. Documented here
  explicitly so a future reviewer doesn't mistake it for the rule being broken.
- Async throughout; full type hints; mypy strict clean.
- Every tenant-scoped query filters `workspace_id` at the service layer, including the
  new `ApiKey`/`AgentRun` (via `Incident.workspace_id`) lookups.
