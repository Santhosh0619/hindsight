# PRD: Hardening

Phase: 14
Module codes: cross-cutting — touches `auth` (B2), `incidents` (B11), `llm` (B12),
every list endpoint across B3–B17 (from plan.md §6). No new F<X> screen.

## Problem

Every prior phase built a real feature against the happy path; none of them asked "what
happens when this endpoint is hit by something other than the app's own frontend
behaving well." Concretely, today: `/auth/login` and `/auth/signup` have no rate limit
at all (only `/auth/demo` does, from Phase 11's narrower guest-provisioning concern),
so credential-stuffing or signup-spam has no backstop; an uncaught exception anywhere
in the app falls through to FastAPI's bare default 500 response with no structured log,
no correlation id, and no guarantee against leaking an internal message; CORS accepts
every HTTP method and header (`allow_methods=["*"]`, `allow_headers=["*"]`) rather than
the specific set this API actually uses; no response carries the standard defensive
security headers (`X-Content-Type-Options`, `X-Frame-Options`, etc.); nothing bounds
the size of an arbitrary request body beyond one Pydantic field-level check on
postmortem text; and outbound calls to LLM providers have no explicit, documented
timeout. This phase closes those gaps — plus verifies, rather than assumes, that the
list endpoints built across 13 phases don't have an N+1 query problem, and builds a
generic mechanism so a future endpoint that forgets its `workspace_id` filter fails a
test immediately instead of shipping a cross-tenant data leak.

## Actors

- **Any unauthenticated caller** — subject to the new auth-endpoint rate limits; never
  sees an internal exception detail, ever.
- **Any authenticated workspace member** — subject to the new brief-generation rate
  limit (distinct from Phase 11's demo-only bucket); every response they receive
  carries a correlation id and the new security headers.
- **A future contributor to this codebase** — the generated tenant-isolation test and
  the query-count regression guard exist specifically to catch *their* mistake before
  it ships, not just to document today's correctness.

## Functional Requirements

FR-01: `POST /auth/login`, `/auth/signup`, and `/auth/refresh` are rate-limited per
client IP (reusing the `TokenBucket` primitive Phase 11 already built and explicitly
earmarked for this phase), returning 429 with `RateLimitedError` past the threshold —
mirroring `/auth/demo`'s existing pattern rather than inventing a second mechanism.

FR-02: `POST /workspaces/{id}/incidents/{id}/brief` and its `/brief/stream` sibling are
rate-limited per workspace, independent of Phase 11's demo-only `demo_brief_bucket` —
a real (non-demo) workspace generating briefs faster than a human plausibly would is
the thing this bounds; the demo carve-out's own limit is untouched.

FR-03: A global exception handler catches every exception `AppError` doesn't (i.e. any
unexpected bug), logs it server-side with the full traceback and the request's
correlation id, and returns a generic `{"error": {"code": "internal_error", ...}}`
envelope that never includes the exception's own message or a stack trace. Every error
response — from `AppError` subclasses and from this new catch-all alike — carries a
`request_id` field in its JSON body, not just the existing `X-Request-ID` header.

FR-04: Every response carries `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and (only
when `cookie_secure` is true, i.e. not local plain-HTTP dev)
`Strict-Transport-Security`.

FR-05: CORS's `allow_methods`/`allow_headers` are the specific set this API actually
uses (`GET`, `POST`, `PATCH`, `DELETE` / `Content-Type`, `Authorization`, `X-API-Key`),
not `["*"]`. `allow_origins` is unchanged — already an explicit env-driven allowlist
since Phase 2.

FR-06: A global middleware rejects any request whose `Content-Length` exceeds a
configured cap (`max_request_bytes`, distinct from and larger than the existing
per-field `max_upload_bytes` postmortem check) with 413, before the body is ever
parsed into a Pydantic model.

FR-07: Every outbound LLM provider call carries an explicit, documented timeout — no
provider call can hang a request indefinitely waiting on a slow or dead upstream.

FR-08: A documented N+1 audit across every list endpoint in the codebase (postmortems,
incidents, agent-runs, catalog services/graph/blast-radius, workspace members,
audit-log, evaluation runs, dashboard aggregates) — verified by direct code reading,
not assumed — plus a regression-guard test that counts SQL statements issued per
request for a representative list endpoint and fails if that count grows unbounded
with row count.

FR-09: A generated cross-tenant-isolation test iterates FastAPI's own route table at
test time to find every endpoint whose path includes a resource id nested under a
workspace, and mechanically asserts that workspace A's session gets 404 (never a
resource from workspace B) when it requests that resource by id — so a new endpoint
that forgets its `workspace_id` filter fails this test automatically, without anyone
having to remember to hand-write a case for it.

## User Stories

As the person whose name is on this project, I want the auth endpoints and brief
generation to survive being hit far harder than a real user ever would, so that a
demo/portfolio deployment reachable from the open internet doesn't fall over or leak
data to casual abuse.

As a future contributor (including a future version of the assistant building later
phases), I want a test that automatically checks every endpoint's tenant isolation, so
that adding a new endpoint without a `workspace_id` filter is caught by `make test`,
not discovered in production.

As anyone debugging a production error, I want every error response to carry a
correlation id I can grep the structured logs for, so that "which request was this"
is never a guess.

## Out of Scope

- A distributed/shared rate limiter (Redis-backed token buckets). The existing
  in-memory, single-process `TokenBucket` is an accepted limitation at this project's
  scale — see NFR "Reliability" and Phase 2's own NFR precedent for the same call.
- File-type/MIME validation on uploads. This app has no binary file-upload endpoint —
  postmortems are pasted text (`raw_text: str`), not uploaded files — so "upload type
  validation" from Master-Prompt.md's phrasing doesn't apply; noted here so a future
  reviewer doesn't treat its absence as a gap.
- A Content-Security-Policy header. The API serves no HTML/JS itself (the frontend is a
  separately-hosted SPA); a CSP on a JSON API has no meaningful effect and would only
  add noise.
- Retrofitting every historical list endpoint's tests with a query-count assertion —
  FR-08's regression guard covers one representative, genuinely list-shaped endpoint as
  a template; the audit itself (reading every service function) is what actually
  verifies the rest, not a mechanically duplicated test per endpoint.

## Acceptance Criteria

- Hitting `/auth/login` past its rate limit returns 429 with `RateLimitedError`'s
  envelope, including a `request_id`; hitting it under the limit is unaffected.
- Triggering an unhandled exception in a test returns the generic `internal_error`
  envelope with a `request_id` and never echoes the original exception's message.
- Every response (success or error) carries `X-Content-Type-Options`,
  `X-Frame-Options`, and `Referrer-Policy`; `Strict-Transport-Security` appears only
  when `cookie_secure` is true.
- The generated tenant-isolation test fails (red) if a `workspace_id` filter is
  deliberately removed from any covered service function during development, and
  passes (green) against the current, correct codebase.
- `make test` stays green; `ruff`/`mypy --strict` stay clean.
