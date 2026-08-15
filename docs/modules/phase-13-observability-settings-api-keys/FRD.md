# FRD: Observability, Settings, API Keys

## API Endpoints (Backend — FastAPI)

### `GET /workspaces/{workspace_id}/agent-runs`
- Auth required: yes, any role.
- Request schema: query `cursor: str | None`, `limit: int = 20` (cursor pagination,
  same `CursorPage`/`encode_cursor`/`decode_cursor` convention as postmortems/audit-log).
- Response schema: `CursorPage[AgentRunOut]` — id, incident_id, incident title, status,
  started_at, finished_at, total_tokens_in, total_tokens_out, from_cache (resolved from
  the run's incident's latest `Brief.from_cache`).
- Error codes: 401, 404 (cross-tenant workspace id).

### `GET /workspaces/{workspace_id}/agent-runs/{run_id}`
- Auth required: yes, any role.
- Response schema: `AgentRunDetailOut` — the list fields plus
  `steps: list[AgentRunStepOut]` (seq, node_name, status, latency_ms, tokens_in,
  tokens_out, output_summary, error), ordered by `seq`.
- Error codes: 401, 404 (run not found, or found but its incident belongs to a
  different workspace).

### `GET /workspaces/{workspace_id}/agent-runs/stats`
- Auth required: yes, any role.
- Response schema: `AgentRunStatsOut` — `total_runs`, `total_tokens_in`,
  `total_tokens_out`, `cache_hit_rate: float | None` (null when `total_runs == 0`,
  never a misleading `0.0`).
- Error codes: 401, 404.

### `POST /workspaces/{workspace_id}/apikeys`
- Auth required: yes, OWNER only.
- Request schema: `ApiKeyCreate { name: str }`.
- Response schema: `ApiKeyCreatedOut { id, name, prefix, raw_key, created_at }` — the
  only response in this module that ever carries `raw_key`; every other read returns
  `ApiKeyOut` (no raw key field at all, not even redacted).
- Error codes: 401, 403 (non-owner), 404.

### `GET /workspaces/{workspace_id}/apikeys`
- Auth required: yes, OWNER only (a key is a credential with full workspace ingest
  access — visibility of *which keys exist* is an owner-level concern, unlike the
  read-only member/audit-log/agent-run screens).
- Response schema: `list[ApiKeyOut]` — id, name, prefix, created_by, created_at,
  last_used_at, revoked_at.
- Error codes: 401, 403, 404.

### `DELETE /workspaces/{workspace_id}/apikeys/{key_id}`
- Auth required: yes, OWNER only.
- Response: 204. Sets `revoked_at`, never deletes the row (audit trail; matches
  `RefreshToken.revoked_at`'s Phase 2 precedent).
- Error codes: 401, 403, 404 (key not found, or found but the wrong workspace), 409
  (already revoked — a second revoke is a no-op conflict, not a silent success).

### `POST /workspaces/{workspace_id}/settings/llm/test`
- Auth required: yes, OWNER only.
- Request schema: none.
- Response schema: `list[LLMProviderTestOut]` — one entry per provider slot
  (`gemini`/`groq`/`ollama`), each `{ provider, configured: bool, ok: bool | None,
  latency_ms: int | None, error: str | None }`. `ok`/`latency_ms`/`error` are all
  `None` when `configured` is `False` — an unconfigured slot is never tested.
- Error codes: 401, 403, 404. Never 503 — a provider failing its own test is reported
  in the response body (`ok: false`), not raised as `LLMUnavailableError`.

### `POST /ingest/postmortem` (new top-level router, not under `/workspaces/{id}`)
- Auth required: yes, but via `X-API-Key` header, never `Authorization`/cookie. The
  workspace is *resolved from the key*, not taken from the URL — an external caller
  only knows its own key, never a workspace id.
- Request schema: `PostmortemCreate` (Phase 5, unchanged — title/raw_text/
  external_ref/occurred_at/duration_minutes/severity).
- Response schema: `PostmortemOut` (same as the session-authenticated create route).
- Error codes: 401 (missing/unknown/revoked key), 422 (validation, identical to the
  session route's).

## React Components (Frontend)

### `pages/AgentRuns.tsx` (F12)
- Props: none (route component).
- API calls: `listAgentRuns(workspaceId)`, `getAgentRunStats(workspaceId)`,
  `getAgentRun(workspaceId, runId)` for the selected run's detail (default: none
  selected, detail panel empty-stated until a row is clicked — matches Evaluation's
  no-forced-selection precedent, but here nothing needs a default since there's no
  natural "most recent" the way Evaluation's ablation table needed one).
- States: selected run id, loading/error/empty per `Dashboard.tsx`'s convention.
- User interactions: click a run row to load its waterfall in a side/below panel.

### `components/agent-runs/RunStatsCards.tsx`
- Props: `stats: AgentRunStatsOut | null`.
- Renders total runs, total tokens, cache hit rate as `MetricCard`s — reuses the exact
  component `dashboard`/`evaluation` already established. `cache_hit_rate: null`
  renders `"—"`, never `0%` (same null-vs-zero discipline as Phase 12's groundedness).

### `components/agent-runs/RunsTable.tsx`
- Props: `runs: AgentRunOut[]`, `onSelectRun: (runId: string) => void`.
- One row per run: incident title, status pill, duration, total tokens, a cache-hit
  badge when `from_cache`.

### `components/agent-runs/RunWaterfall.tsx`
- Props: `run: AgentRunDetailOut | null`.
- One row per step in `seq` order: node name, status, latency, tokens in/out, a
  one-line `output_summary` rendering (retrieval count / candidate count / hypothesis
  count, whichever key that node's summary actually carries).

### `pages/Settings.tsx` (F13)
- Props: none.
- API calls: reuses Phase 2's `listMembers`/`inviteCode`/`changeRole`/`removeMember`/
  `updateWorkspace`/`deleteWorkspace` (adding thin `lib/api.ts` wrappers where Phase 2
  built the backend route but no frontend call yet existed), plus new
  `listApiKeys`/`createApiKey`/`revokeApiKey`/`testLlmProviders`.
- States: per-panel loading/error (members panel, API keys panel, LLM panel, danger
  zone), a `justCreatedKey` string held only in memory for the "shown once" flow.
- User interactions: invite/role-change/remove a member; rotate invite code; create/
  revoke an API key; run the LLM connection test; type-to-confirm workspace deletion.
- Role gating: every write action in every panel is hidden for non-owners (the whole
  page is owner-only per FR-07/plan.md §13's original scope — a responder/viewer sees
  a read-only members list and nothing else, matching `AppShell`'s existing
  `useRequireRole`-gated nav entry for Settings from Phase 3).

### `components/settings/MembersPanel.tsx`, `ApiKeysPanel.tsx`, `LlmProviderPanel.tsx`,
`DangerZonePanel.tsx`
- Each owns one FR-07 sub-area; composed into `Settings.tsx`. `ApiKeysPanel`'s create
  flow shows the raw key exactly once in a copyable, dismiss-to-continue banner —
  never re-fetchable, never logged to the console.

### `pages/AuditLog.tsx` (F14)
- Props: none.
- API calls: `getAuditLog(workspaceId, { cursor, actor?, action?, targetType? })` —
  extends the existing Phase 2 endpoint's query params (currently cursor/limit only)
  with the three filters this FRD adds server-side (see Data Model / Internal
  Architecture — filtering client-side against one page of 50 rows would silently miss
  matches on earlier pages).
- States: filter values, loading/error/empty, cursor-based "load more".

## Data Model Changes

No new tables — `agent_runs`, `agent_run_steps`, `api_keys`, `audit_log` all already
exist from Phase 1's initial migration, unused or under-used until now. No column
additions either: `agent_run_steps.tokens_in`/`tokens_out` already exist, simply never
populated with a real value before this phase (see Internal Architecture).

`GET /workspaces/{id}/audit-log` gains three optional query params (`actor_user_id`,
`action`, `target_type`) translated into `WHERE` clauses in `workspace_service
.list_audit_log`, applied before pagination — an addition to an existing function's
signature, not a schema change.

## Internal Architecture

### Real per-step token usage (retrofits Phase 8's agents, not just Phase 13 code)

- `LLMProvider` protocol (`app/services/llm/provider.py`) gains a second method,
  `structured_with_usage(prompt, *, system, result_type) -> tuple[T, LLMResponse]`,
  additive alongside the existing `structured()` — every provider
  (`gemini.py`/`groq.py`/`ollama.py`) already computes `result.usage.input_tokens/
  output_tokens` inside `.complete()` today and simply never returns it from
  `.structured()`; the new method returns both. `LLMRouter.structured_with_usage`
  mirrors `LLMRouter.structured`'s `_try_providers` plumbing.
- `extract_signal`/`draft_brief`/`judge_verification` (`app/agents/
  {normalizer_agent,analyst_agent,critic_agent}.py`) switch to the new method and
  return `tuple[ResultType, LLMResponse]`. `normalizer_node`/`analyst_node`/
  `critic_node` (`app/agents/nodes.py`) each include `step_tokens_in`/
  `step_tokens_out` in their returned state-update dict — `0` on every path that never
  actually called an LLM this pass (cache hit, `llm_used=False`, LLM became
  unavailable mid-run), matching the honest-zero discipline the checkpoint's
  acceptance criterion calls for. `retriever_node`/`correlator_node`/`briefer_node`
  never call an LLM and don't set these keys at all — `AgentRunStep`'s default of `0`
  already means "correctly, structurally, no LLM cost," not a missing value.
- `stream_graph_events` (`app/agents/streaming.py`) reads `output.get("step_tokens_in",
  0)`/`output.get("step_tokens_out", 0)` from each node's own returned dict — this is
  the raw per-node return value `astream_events` already hands the observer loop, not
  the graph's cumulative merged state, so no extra plumbing is needed to keep these
  scoped to the step that actually produced them. `AgentRun.total_tokens_in/out` are
  updated in `_finish_agent_run` by summing the run's own `AgentRunStep` rows.
- `_summarize(output)` (`streaming.py`) is extended per node: `retriever` includes
  `result_count`; `correlator` includes `candidate_count` and the top candidate's
  `overall_score`; `analyst` includes `hypothesis_count`; `critic` includes `score`
  and `invalid_citation_count`. Still never the full retrieved text/prompt — a
  summary, per the existing docstring's own stated constraint.

### `app/services/apikey_service.py`

- `generate_key() -> tuple[str, str, str]` returns `(raw_key, prefix, key_hash)` —
  `raw_key` is `secrets.token_urlsafe(32)` prefixed with a fixed `hs_` marker (a
  recognizable, greppable prefix, the same idea as Stripe/GitHub token prefixes, not a
  security control); `prefix` is the first 12 characters of the raw key (shown in
  `ApiKeyOut` so an owner can tell keys apart without ever seeing the full value
  again); `key_hash` is `hashlib.sha256(raw_key).hexdigest()`, **not** argon2 — API
  keys are already 256 bits of real entropy, not a low-entropy human password, so the
  slow-hash protection argon2 buys against offline brute force isn't needed, and a
  fast hash is what a high-frequency-lookup-by-hash access path (every webhook call)
  actually wants. See NFR "Security" for the full argument.
- `create_key`, `list_keys`, `revoke_key` — straightforward CRUD, each writing an
  `audit_log` entry (`api_key.created`/`api_key.revoked`) via the existing
  `write_audit_log` helper from Phase 2.
- `authenticate_key(db, raw_key) -> Workspace` — hashes the presented key, looks it up
  by `key_hash`, checks `revoked_at is None`, updates `last_used_at`, returns the
  owning workspace. Raises `UnauthorizedError` for unknown/revoked keys — the same
  error shape whether the key never existed or was revoked, so a caller can't
  distinguish "wrong key" from "right key, revoked" (no information leak either way).

### `app/api/v1/ingest.py`

- New top-level router (`prefix="/ingest"`, mounted directly on `app`, not nested
  under `/workspaces/{id}` — the workspace comes from the key, not the URL).
  `get_api_key_workspace` (new `core/deps.py` dependency) reads `X-API-Key`, calls
  `apikey_service.authenticate_key`, returns the `Workspace`. The route itself calls
  `postmortem_service.create_postmortem(db, workspace_id=workspace.id,
  created_by=api_key.created_by, payload=payload)` — the exact function the
  session-authenticated route already calls, so ingestion behavior (validation,
  redaction, chunking, embedding, job enqueue) is identical by construction, not by
  parallel reimplementation. `created_by` is nullable (matches `Postmortem
  .created_by`'s existing nullability) since a key's creator account could later be
  removed from the workspace without invalidating the key.

### `app/services/llm_test_service.py`

- `test_provider(provider: LLMProvider) -> LLMProviderTestOut` calls `.complete()`
  with a fixed trivial prompt (`"Reply with the single word: ok"`) and a short system
  prompt, times it, and reports `ok=True` on any successful response (not checking the
  reply text — the point is reachability/auth, not model quality) or `ok=False` with
  the exception message on failure. `test_all_providers(settings) -> list[...]`
  constructs each of the three providers directly (bypassing `LLMRouter`'s fallback
  entirely, per FR-09) and marks a slot `configured=False` without calling it at all
  when its required setting (`llm_api_key`/`groq_api_key`) is absent — Ollama is
  always "configured" (no key required) but its `ok` can still be `False` if
  unreachable.

## Dependencies

- Calls: `app.services.postmortem_service.create_postmortem` (Phase 5, unmodified),
  `app.services.workspace_service.write_audit_log`/`list_audit_log` (Phase 2, the
  latter extended with filter params), `app.services.llm.router.LLMRouter`/individual
  provider classes (Phase 6).
- Called by: F12/F13/F14 (read + owner-only writes), external systems via
  `POST /ingest/postmortem` (new, unauthenticated by session — API-key only).

## Sequence Flows

### API key ingest webhook
1. External system `POST /ingest/postmortem` with `X-API-Key: hs_...` and a
   `PostmortemCreate` body.
2. `get_api_key_workspace` hashes the key, looks up `ApiKey` by `key_hash`, checks
   `revoked_at is None`, updates `last_used_at`, resolves the `Workspace`.
3. Route calls `postmortem_service.create_postmortem` — identical to the session path:
   `Postmortem` row created `PENDING`, `ingest_postmortem` job enqueued.
4. Worker claims the job exactly as it would for a session-created postmortem;
   `status` progresses `pending → processing → indexed` the same way.
5. Revoking the key (`DELETE .../apikeys/{id}`) sets `revoked_at`; the next request
   with that key fails at step 2 with 401, before any postmortem row is touched.

### An agent run's token trail, end to end
1. `analyst_node` calls `extract_...`/`draft_brief` via `structured_with_usage`,
   returns `{"draft": ..., "step_tokens_in": N, "step_tokens_out": M, ...}` (or `0/0`
   on a cache hit — the semantic cache path never calls the LLM this pass).
2. `stream_graph_events` reads those two keys straight off the node's own `output`
   dict, writes them onto that step's `AgentRunStep` row.
3. `_finish_agent_run` sums all of the run's `AgentRunStep.tokens_in/out` into
   `AgentRun.total_tokens_in/out`.
4. `GET .../agent-runs/stats` sums `AgentRun.total_tokens_in/out` across every run in
   the workspace, and computes `cache_hit_rate` from the fraction of runs whose
   incident's latest `Brief.from_cache` is `true`.

## Edge Cases & Error Handling

- **A run with zero LLM calls at all** (no key configured the whole way through):
  every step's tokens are honestly `0`, `AgentRunStatsOut.cache_hit_rate` still
  computes normally (a `from_cache=False`, `llm_used=False` run is neither a cache hit
  nor miss in the meaningful sense, but it's also not silently excluded — it's counted
  as a non-hit, which is what actually happened).
- **Revoking an already-revoked key**: 409, not a silent 204 — matches this
  codebase's existing "a second identical mutation is a conflict, not a no-op"
  convention (e.g. Phase 11's `demo_brief_bucket` exhaustion, Phase 2's join-twice
  test).
- **The ingest webhook receives a key that authenticates but the workspace was since
  deleted**: can't happen — `ApiKey.workspace_id` has `ondelete="CASCADE"`, so a
  deleted workspace's keys are gone with it, and a gone key is just "unknown key" (401)
  at lookup time, not a dangling reference to handle specially.
- **LLM connection test against a slot with no key at any point** (Ollama with nothing
  running at `ollama_base_url`): `ok=False`, `error` carries the connection failure
  message, never raised as a 503 — a failed diagnostic result is the entire point of
  the endpoint, not an error condition for the endpoint itself.
- **Workspace deletion confirmation text mismatch**: rejected client-side before the
  request is even sent (matches "typed confirmation" from Master-Prompt.md literally);
  the backend's existing `DELETE /workspaces/{id}` has no knowledge of the confirmation
  text at all — that's a frontend gate in front of an already-real, already-owner-gated
  delete, the same layering `NewPostmortemModal`'s client-side size check uses in front
  of the server's own `max_upload_bytes` enforcement.
