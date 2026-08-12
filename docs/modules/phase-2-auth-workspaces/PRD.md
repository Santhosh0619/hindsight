# PRD: Auth & Workspaces
Phase: 2
Module codes: B3 (`auth`), B4 (`workspaces`) from plan.md §6

## Problem

Nothing in the product is usable without an identity and a tenant boundary. A user
needs to sign up, log in, and stay logged in safely across sessions; every later
resource (services, postmortems, incidents, briefs) belongs to a workspace, and every
request against it must resolve who the caller is and whether they're allowed to touch
that workspace at all. Phase 1 built the primitives (`argon2` hashing, JWT encode/decode,
the `get_current_user`/`get_current_workspace`/`require_role` dependencies) but wired up
nothing that actually creates a user or a session.

## Actors

- An unauthenticated visitor, signing up or logging in.
- An authenticated user, managing their own workspaces and memberships.
- A workspace owner, managing members' roles and generating invite codes.
- A demo guest — an auto-provisioned, rate-limited, read-mostly session on the seeded
  demo workspace (full seeding lands in Phase 11; this phase provisions the guest
  identity and role against whatever demo workspace exists, seeded or not).
- Every later backend module, which depends on this phase's auth/tenancy resolution
  and audit-log writer rather than reimplementing them.

## Functional Requirements

FR-01: `POST /auth/signup` creates a user (argon2id-hashed password), a personal
workspace they own, and returns an access token; the refresh token is set as an
httpOnly cookie. No email verification (documented scope decision, ADR).

FR-02: `POST /auth/login` verifies credentials and returns the same access-token /
refresh-cookie pair as signup. Wrong email and wrong password return the same 401
message so a caller can't distinguish "no such user" from "wrong password".

FR-03: `POST /auth/refresh` reads the refresh cookie, verifies its hash against
`refresh_tokens`, revokes that row, and issues a new access token plus a new refresh
cookie (rotation). Presenting an already-revoked refresh token revokes every other
non-revoked token for that user (reuse detection — a stolen, already-used token can't
be replayed to extend a session).

FR-04: `POST /auth/logout` revokes the presented refresh token and clears the cookie.

FR-05: `POST /auth/demo` provisions an ephemeral guest user (`is_demo=True`) attached
to the workspace flagged `is_demo=True` (creating a minimal placeholder demo workspace
if none exists yet — full corpus seeding is Phase 11) as a `viewer` member, and returns
the same token pair as signup/login. Rate-limited by caller IP.

FR-06: `GET /auth/me` returns the caller's user record and their workspace
memberships.

FR-07: `POST /workspaces` creates a workspace and adds the caller as `owner`.
`GET /workspaces` lists workspaces the caller is a member of. `GET /workspaces/{id}`
returns one (404 if not a member). `PATCH /workspaces/{id}` (owner only) updates
name/slug. `DELETE /workspaces/{id}` (owner only) deletes the workspace and everything
under it via cascade.

FR-08: `GET /workspaces/{id}/members` lists members and roles (any member).
`POST /workspaces/{id}/members/invite-code` (owner only) issues/rotates a single-use*
invite code for the workspace. `POST /workspaces/join` redeems a valid code and adds
the caller as a `responder`. `PATCH /workspaces/{id}/members/{user_id}` (owner only)
changes a member's role. `DELETE /workspaces/{id}/members/{user_id}` (owner only)
removes a member; an owner cannot remove themself while they're the workspace's only
owner (a workspace must always have at least one owner).

FR-09: Every mutation in this module (workspace create/update/delete, member
add/role-change/remove, invite-code rotation) writes one `audit_log` row: actor,
action, target type/id, and a small `meta` payload.

FR-10: `GET /workspaces/{id}/audit-log` returns the workspace's audit log, paginated,
to any member.

*"Single-use" here means single-active-code-per-workspace (rotating issues a new code
and invalidates the previous one), not single-redemption — anyone holding the current
code can join once. A per-redemption single-use invite is out of scope for this phase.

## User Stories

- As a new user, I want to sign up and land in my own workspace immediately, so I can
  start using the product without waiting on an email I'd never get anyway (no mail
  service is free/reliable — see ADR).
- As a returning user, I want my session to survive a browser restart without having to
  re-enter my password, and I want a stolen refresh token to stop working the moment
  it's used once by someone else.
- As a workspace owner, I want to invite teammates with a code instead of needing their
  user IDs, and I want to see who did what in the audit log.
- As a recruiter/demo visitor, I want a one-click path into a working workspace with no
  signup friction.
- As any later backend module's author, I want `get_current_workspace`/`require_role`
  (already built) to be the only tenancy check I ever have to write.

## Out of Scope

- Email verification, password reset via email, OAuth/social login — no free, reliable
  mail service; documented as a deliberate scope decision.
- Per-redemption single-use invite codes / invite-by-email — one active code per
  workspace is enough for this phase's demo scope.
- The frontend auth screens (F2) and onboarding (F3) — Phase 3.
- Rate-limiting infrastructure beyond a simple in-memory bucket for `/auth/demo` — the
  full rate-limiting story (auth endpoints generally, brief generation) is Phase 14.
- Seeding the actual demo corpus — Phase 11. This phase only needs *a* demo workspace
  to exist for `/auth/demo` to attach guests to.

## Acceptance Criteria

1. `curl` through signup → login → refresh → logout works end-to-end, refresh cookie
   rotates every call, and replaying a spent refresh token 401s and revokes the rest of
   that user's active refresh tokens.
2. A `viewer` gets 403 on every workspace-mutating endpoint; a non-member of a
   workspace gets 404 (not 403) on any of its endpoints.
3. `/auth/demo` returns a working session with no prior signup.
4. Every mutation covered by FR-09 produces exactly one `audit_log` row.
5. `ruff check .`, `mypy app --strict`, and `pytest` are all clean.
