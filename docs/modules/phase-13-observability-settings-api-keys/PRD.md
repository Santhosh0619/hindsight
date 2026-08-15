# PRD: Observability, Settings, API Keys

Phase: 13
Module codes: B15 / B16 / F12 / F13 / F14 (from plan.md §6)

## Problem

Three gaps stand between Hindsight and a workspace an operator could actually run day
to day. First, the agent pipeline (Phase 8) already executes six real nodes per brief
and already has `agent_runs`/`agent_run_steps` tables (Phase 1) sitting empty of
anything but latency — nobody can see what a run actually cost in tokens, whether it
hit the semantic cache, or what it retrieved, which is exactly the free-tier-quota
awareness a real operator needs and a portfolio reviewer wants to see tracked. Second,
workspace administration is scattered: member/role/invite management and the audit
log already work end-to-end from Phase 2 but have no screen, and there is no way to
delete a workspace from the UI or see which LLM providers are actually reachable right
now. Third, and the reason this phase exists at all: every postmortem today can only
enter the system through an authenticated browser session. A CI pipeline, a chatops
bot, or any other external system that wants to push a postmortem the moment an
incident closes has no way in.

## Actors

- **Owner** — the only role that manages members/roles, creates/revokes API keys,
  changes LLM provider settings, and deletes the workspace.
- **Any workspace member** — reads Agent Runs and the audit log; these are operational
  visibility, not a write surface (mirrors Phase 12's Evaluation page precedent).
- **External system** (CI, chatops bot, another service) — authenticates with a
  workspace API key, never a user session, to push a postmortem via the new webhook.

## Functional Requirements

FR-01: Every real agent-pipeline run (Phase 8/9) now records, per node it actually
executed, the tokens the LLM call it made consumed (0 for nodes that never call an
LLM, or didn't this pass) and a compact summary of what it retrieved/produced — not
just latency, which is all `agent_run_steps` captures today.

FR-02: `GET /workspaces/{id}/agent-runs` lists runs (most recent first, paginated) with
each run's status, duration, total tokens, and whether its brief was served from
cache. `GET /workspaces/{id}/agent-runs/{run_id}` returns the full per-step waterfall
for one run.

FR-03: `GET /workspaces/{id}/agent-runs/stats` returns workspace-wide aggregates: total
tokens in/out across all runs, and cache hit rate (fraction of runs whose brief was
served from the semantic cache).

FR-04: `POST /workspaces/{id}/apikeys` creates a new API key, returning the raw key
exactly once; only its hash is ever stored. `GET .../apikeys` lists keys (name,
prefix, creator, last-used, revoked status — never the raw key again).
`DELETE .../apikeys/{id}` revokes a key immediately and irreversibly.

FR-05: `POST /ingest/postmortem` accepts a postmortem authenticated by
`X-API-Key: <raw key>` instead of a session — no `Authorization` header, no cookie.
A revoked or unknown key gets 401. A valid key resolves to its workspace and runs the
exact same `create_postmortem` path a session-authenticated `POST
/workspaces/{id}/postmortems` already does (same validation, same job-queue
enqueue), so the postmortem ingests identically regardless of which door it came
through.

FR-06: F12 Agent Runs page lists runs with the aggregates from FR-03 shown up top;
clicking a run shows its step-by-step waterfall (latency, tokens, retries, a compact
view of what was retrieved) in execution order.

FR-07: F13 Settings page exposes, behind existing Phase 2 endpoints: member
list/invite/role-change/remove, workspace rename, and workspace deletion gated by
typing the workspace's own name/slug to confirm. It adds two things Phase 2 didn't
build: the API keys panel (FR-04) and an LLM Provider panel showing each of the three
provider slots (Gemini/Groq/Ollama) with its configured/not-configured status and a
"Test connection" action per slot.

FR-08: F14 Audit Log page lists `workspace_audit_log` entries (already written by
every mutating action since Phase 2) with client-side filters by actor, action, and
target type, paginated via the existing cursor endpoint.

FR-09: `POST /workspaces/{id}/settings/llm/test` (owner-only) attempts a trivial
completion against each of the three provider slots independently and reports
success/failure/latency per slot — never against the router's fallback chain, since
that would hide which specific provider actually answered.

## User Stories

As an owner, I want to see how many tokens brief generation is actually costing me and
whether the cache is doing its job, so that I can reason about free-tier quota before
I hit it, not after.

As an owner, I want to create a scoped API key and push a postmortem into Hindsight
from a script, so that closing an incident in some other tool can automatically hand
Hindsight the postmortem instead of someone remembering to paste it in later.

As any workspace member, I want to see the audit log and a past agent run's real
step-by-step trace, so that "what actually happened" is never a mystery I have to
reconstruct from application logs.

## Out of Scope

- Rotating/regenerating an existing API key in place (revoke-and-recreate is the only
  path, mirroring the invite-code rotation precedent from Phase 2 — simpler than a
  rotation flow with its own overlap window).
- Per-workspace LLM provider *preference* persisted to the database. Provider
  configuration remains env-level/global (plan.md's three-tier graceful-degradation
  model, unchanged since Phase 6); F13's LLM panel is read/diagnose only — see FR-09.
- Scoping an API key to a subset of permissions (e.g. ingest-only vs. full workspace
  access). Every key in this phase is workspace-wide, matching plan.md §8's `api_keys`
  schema, which carries no scope column.
- Metrics/tracing export to an external observability backend (Prometheus, OTel). F12
  is Hindsight's own UI over its own tables, not an integration.

## Acceptance Criteria

- Master-Prompt.md's own checkpoint: create an API key, `POST` a postmortem with it,
  watch it ingest through the real pipeline, revoke the key, confirm the next request
  with it 401s.
- A real agent run's F12 detail view shows nonzero tokens for at least the
  analyst/critic steps when an LLM key is configured, and an honest zero (not a
  missing field) for every step when it isn't.
- F13's workspace deletion cannot succeed without typing the exact workspace
  name/slug; F14's filters actually narrow the visible rows against real audit-log
  data.
