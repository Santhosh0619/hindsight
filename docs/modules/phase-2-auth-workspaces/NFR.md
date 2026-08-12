# NFR: Auth & Workspaces

## Performance

- Every endpoint in this phase does 1-3 indexed lookups (`users.email`,
  `refresh_tokens.token_hash`, `workspace_members` composite PK, `workspaces.invite_code`)
  — no N+1 risk at this phase's scale. `list_members`/`list_audit_log` are the only
  list endpoints; audit-log uses the existing cursor-pagination helper so it stays cheap
  as the table grows.
- Argon2id hashing is deliberately slow (~100-300ms) by design — never called outside
  `signup`/`login`, never in a hot path or a loop.
- `/auth/demo`'s rate limiter is an in-memory dict, O(1) per check — fine for a single
  worker process; documented as not shared across replicas (see Reliability).

## Security

- Passwords: argon2id via `argon2-cffi` (Phase 1 primitive, unchanged).
- Refresh tokens: opaque, SHA-256-hashed at rest (Phase 1 primitive); rotation +
  reuse-family-revocation implemented in this phase per FR-03.
- Refresh cookie: `httpOnly`, `Secure`, `SameSite=Lax`, scoped to `/api/v1/auth` (not
  site-wide) so it's never sent to unrelated endpoints. Access token is never cookied —
  returned in the JSON body only, per plan.md Phase 2's explicit split (kept in memory
  by the frontend in Phase 3).
- Login/refresh error messages are identical regardless of *why* they failed (no user
  enumeration, no "this token was reused" tell).
- Every workspace mutation is gated by `require_role` (Phase 1 dependency) — this phase
  adds no new tenancy-check mechanism, it only uses the existing one consistently.
- Demo-guest accounts get an unusable random password hash (never meant to be logged
  into directly) and are always `viewer` + rate-limited, never `owner`/`responder`.
- Invite codes are `secrets.token_urlsafe`-derived (not guessable), but knowledge of a
  live code is sufficient to join as `responder` — acceptable for this phase's demo
  scope (documented in FRD as an explicit non-goal to make per-invite/per-email codes).

## Reliability

- `auth_service.signup`'s user+workspace+membership insert is one DB transaction — a
  crash mid-signup never leaves an orphaned user with no workspace.
- The demo rate limiter is in-process memory: on a multi-worker/multi-replica deploy
  each process has its own bucket, so the *effective* limit is `bucket_size × replica
  count`. Documented as acceptable for this phase/portfolio scale; Phase 14's real
  rate-limiting pass is where this gets revisited if it matters.
- `refresh` never 500s on a missing/garbage cookie — always a clean 401.

## Observability

- Every mutating call in this module logs via `structlog` (Phase 1's `get_logger`) with
  the actor and target IDs bound, at minimum: `user_signed_up`, `user_logged_in`,
  `refresh_token_reused` (this one at `warning`, not `info` — it's a signal worth
  noticing), `workspace_created`, `workspace_member_role_changed`.
- `audit_log` (FR-09/FR-10) is the durable, queryable record; `structlog` output is the
  operational trace — they serve different audiences and are both populated.

## Testability

- Backend: `auth_service`'s functions are tested against a real test DB (this phase's
  first integration tests that touch actual rows, not just pure functions like Phase
  1's). Covered: signup happy path + duplicate-email conflict; login happy path + wrong
  password + wrong email (same error); refresh rotation; refresh-reuse revokes the
  family; logout; demo-guest provisioning + rate limit; workspace CRUD role matrix
  (owner/responder/viewer × each mutating endpoint); cross-tenant 404; invite-code
  issue/join/already-a-member; last-owner-cannot-be-removed; audit-log row exists after
  each mutation covered by FR-09.
- Frontend: none yet (Phase 3).
- E2E: still deferred per Phase 1's ADR 0001 §4 — `docker-compose.test.yml` needs
  `frontend/package.json` (Phase 3). This phase's acceptance criteria are verified by
  its own `pytest` integration suite plus the manual `curl` walkthrough in the PRD.

## Constraints

- Everything from Phase 1's NFR still applies (async throughout, Pydantic v2 at every
  boundary, typed exceptions, one Postgres database, zero paid services, `mypy --strict`
  clean).
- No new external dependency — `secrets` (invite codes) and a hand-rolled token-bucket
  are stdlib/trivial; no rate-limiting library, no session store beyond `refresh_tokens`.
- Migration for `workspaces.invite_code` is a new revision chained after `b9e49c30b2c7`
  — never edits that already-merged migration.
