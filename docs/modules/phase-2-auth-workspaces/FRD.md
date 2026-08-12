# FRD: Auth & Workspaces

## API Endpoints (Backend — FastAPI)

### `POST /auth/signup`
- Auth required: no
- Request: `SignupRequest{email: EmailStr, password: str (min 8), full_name: str (1-200)}`
- Response `201`: `AuthResponse{access_token: str, token_type: "bearer", user: UserOut}`
  (`UserOut{id, email, full_name, is_demo}`); refresh token set via `Set-Cookie`
  (httpOnly, Secure, SameSite=Lax, path=`/auth`, max-age = `refresh_token_ttl_days`).
- Errors: `409 conflict` (email already registered), `422 validation_error` (weak
  password / malformed email — Pydantic-level).

### `POST /auth/login`
- Auth required: no
- Request: `LoginRequest{email: EmailStr, password: str}`
- Response `200`: `AuthResponse` (same shape as signup), refresh cookie set.
- Errors: `401 unauthorized` — identical message whether the email doesn't exist or the
  password is wrong (`"Invalid email or password"`).

### `POST /auth/refresh`
- Auth required: no (reads the refresh cookie itself, not a bearer token)
- Request: none (refresh token comes from the cookie)
- Response `200`: `AuthResponse` (new access token, `user`), new rotated refresh cookie.
- Errors: `401 unauthorized` — missing cookie, hash not found, or already-revoked
  (reuse — see Edge Cases).

### `POST /auth/logout`
- Auth required: no (operates on whatever refresh cookie is present; a missing/invalid
  cookie is treated as already logged out, not an error)
- Response `204`, cookie cleared (`Set-Cookie` with `max-age=0`).

### `POST /auth/demo`
- Auth required: no
- Response `200`: `AuthResponse` for a freshly provisioned demo-guest user, `viewer`
  role on the demo workspace.
- Errors: `429` (rate limit — more than 5 demo provisions per IP per hour), `503
  llm_unavailable`-shaped **no** — reuses `AppError`'s envelope but with its own code
  `demo_unavailable` if no demo workspace exists at all (should not happen once one is
  created; see Internal Architecture).

### `GET /auth/me`
- Auth required: yes (Bearer)
- Response `200`: `MeResponse{user: UserOut, memberships: list[MembershipOut]}`
  (`MembershipOut{workspace_id, workspace_name, workspace_slug, role}`).

### `POST /workspaces`
- Auth required: yes
- Request: `WorkspaceCreate{name: str (1-200)}` (slug is derived, see Internal Architecture)
- Response `201`: `WorkspaceOut{id, name, slug, is_demo, created_at, role: "owner"}`

### `GET /workspaces`
- Auth required: yes
- Response `200`: `list[WorkspaceOut]` — every workspace the caller is a member of,
  `role` reflecting *their* membership in each.

### `GET /workspaces/{workspace_id}`
- Auth required: yes, any member (`get_current_workspace`)
- Response `200`: `WorkspaceOut`
- Errors: `404 not_found` (not a member — existence not confirmed)

### `PATCH /workspaces/{workspace_id}`
- Auth required: yes, `require_role(OWNER)`
- Request: `WorkspaceUpdate{name: str | None, slug: str | None}` (both optional, at
  least one required)
- Response `200`: `WorkspaceOut`
- Errors: `404` (non-member), `403` (member but not owner), `409` (slug collision)

### `DELETE /workspaces/{workspace_id}`
- Auth required: yes, `require_role(OWNER)`
- Response `204`
- Errors: `404`, `403`

### `GET /workspaces/{workspace_id}/members`
- Auth required: yes, any member
- Response `200`: `list[MemberOut]{user_id, email, full_name, role, joined_at}`

### `POST /workspaces/{workspace_id}/members/invite-code`
- Auth required: yes, `require_role(OWNER)`
- Response `200`: `InviteCodeOut{code: str}` — issues a fresh code, invalidating any
  previous one for this workspace.

### `POST /workspaces/join`
- Auth required: yes
- Request: `JoinRequest{code: str}`
- Response `200`: `WorkspaceOut` (the joined workspace, caller's new `role: "responder"`)
- Errors: `404 not_found` (invalid/unknown code — same code as "doesn't exist", no
  distinct "expired" signal), `409 conflict` (already a member)

### `PATCH /workspaces/{workspace_id}/members/{user_id}`
- Auth required: yes, `require_role(OWNER)`
- Request: `RoleUpdate{role: WorkspaceRole}`
- Response `200`: `MemberOut`
- Errors: `404` (member not found), `403`, `409` (would remove the workspace's last
  owner by demoting them)

### `DELETE /workspaces/{workspace_id}/members/{user_id}`
- Auth required: yes, `require_role(OWNER)`
- Response `204`
- Errors: `404`, `403`, `409` (target is the workspace's only owner)

### `GET /workspaces/{workspace_id}/audit-log`
- Auth required: yes, any member
- Query: `cursor: str | None`, `limit: int = 50`
- Response `200`: `CursorPage[AuditLogEntryOut]` (reuses `app.core.pagination.CursorPage`)

All error responses use the existing `{"error": {"code", "message", "detail"}}`
envelope from `app/core/errors.py` (`app_error_handler`, already registered).

## React Components (Frontend)

None — Phase 3 builds F2 (auth screens) and F3 (onboarding) against these endpoints.

## Data Model Changes

New Alembic revision (chained after `b9e49c30b2c7`), one column:
- `workspaces.invite_code: String(20), unique, nullable, indexed` — no dedicated table;
  plan.md §8 doesn't model invite codes separately, and "one active code per workspace,
  regenerable" doesn't need one (see ADR). Nullable because a workspace has no code
  until an owner first requests one.

No other schema changes — `users`, `refresh_tokens`, `workspaces`, `workspace_members`,
`audit_log` already exist from Phase 1's initial migration and match this phase's needs
exactly.

## Internal Architecture

- `app/services/auth_service.py`
  - `signup(db, email, password, full_name) -> tuple[User, str]` — hashes the password,
    creates the `User`, creates a personal `Workspace` (name = `f"{full_name}'s
    workspace"`, slug = a URL-safe slugified/uniquified version of that), adds an
    `owner` `WorkspaceMember` row, issues a token pair. Raises `ConflictError` on a
    duplicate email (caught from the DB's unique constraint, not pre-checked — avoids a
    TOCTOU gap).
  - `login(db, email, password) -> tuple[User, str]` — looks up by email, verifies the
    hash; on any failure (no such user, wrong password, inactive user) raises the same
    `UnauthorizedError("Invalid email or password")` so the two cases are
    indistinguishable from the response.
  - `issue_token_pair(db, user) -> tuple[str, str]` — shared by signup/login/refresh/demo:
    creates the access JWT (`create_access_token`) and a new `RefreshToken` row
    (`generate_refresh_token` + `hash_refresh_token`, `expires_at = now +
    refresh_token_ttl_days`), returns `(access_token, raw_refresh_token)`.
  - `refresh(db, raw_token) -> tuple[User, str]` — hashes the presented token, looks up
    the `RefreshToken` row by hash. Missing row → `UnauthorizedError`. Row exists but
    `revoked_at` is already set → **reuse detected**: revoke every other non-revoked
    `RefreshToken` for that `user_id` (the whole family), then `UnauthorizedError`. Row
    exists and is live → revoke it (`revoked_at = now`), issue a new pair, return.
  - `logout(db, raw_token) -> None` — hash and revoke if found; no-op (not an error) if
    the token is missing/already revoked/unknown, matching FR-04.
  - `create_demo_guest(db) -> tuple[User, str]` — finds the `Workspace` with
    `is_demo=True` (creates a minimal one — name `"Demo Workspace"`, `is_demo=True` — if
    none exists yet, so this phase doesn't hard-depend on Phase 11's seed); creates a
    `User(is_demo=True, email=f"guest-{uuid4().hex[:12]}@demo.hindsight.local",
    password_hash=<unusable random argon2 hash — this account is never logged into by
    password>)`, adds them as `viewer`, issues a token pair.
- `app/services/rate_limit.py` — a small in-memory `TokenBucket` keyed by client IP
  (`X-Forwarded-For` first hop, else `request.client.host`), used only by `/auth/demo`
  in this phase (5 tokens, refill 1/12min ⇒ 5/hour). Explicitly documented as an
  interim, single-process solution — Phase 14 owns the real rate-limiting story project-
  wide (`app/core/errors.py` already returns a stable envelope shape for it to reuse).
- `app/services/workspace_service.py`
  - `create_workspace(db, owner, name) -> Workspace`, `list_my_workspaces(db, user) ->
    list[tuple[Workspace, WorkspaceRole]]`, `update_workspace`, `delete_workspace`
    (owner-role-checked by the route's `require_role` dependency, not re-checked here —
    this layer trusts its caller the same way `catalog_service` etc. will in later
    phases), `list_members`, `rotate_invite_code(db, workspace) -> str` (generates
    `secrets.token_urlsafe(9)`-derived 12-char code, stores it), `join_by_code(db, user,
    code) -> Workspace`, `change_member_role`, `remove_member` (both reject demoting/
    removing a workspace's last `owner` with `ConflictError`), `list_audit_log`
    (cursor-paginated via `app.core.pagination`).
  - `write_audit_log(db, *, workspace_id, actor_user_id, action, target_type, target_id,
    meta) -> None` — the single write path every mutation above calls; FR-09's
    guarantee is enforced by every mutating function calling this before returning, not
    by a generic ORM hook (explicit > implicit for something an interviewer will ask
    about directly).
- `app/api/v1/auth.py`, `app/api/v1/workspaces.py` — thin FastAPI routers: parse
  request, call the service, set/read the refresh cookie, map the service's return value
  to the response schema. No business logic in the route functions themselves.
- `app/schemas/auth.py`, `app/schemas/workspace.py` — the Pydantic v2 request/response
  models listed under Endpoints above.

## Dependencies

Depends on Phase 1's `app.core.security` (hashing/JWT primitives), `app.core.deps`
(`get_current_user`/`get_current_workspace`/`require_role` — already built, unchanged
by this phase), `app.core.errors`, `app.core.pagination`, and the `User`/`RefreshToken`/
`Workspace`/`WorkspaceMember`/`AuditLog` models. Every later module (catalog, ingestion,
incidents, …) depends on this phase's routes existing so there's a way to obtain a
session and a workspace to scope requests to.

## Sequence Flows

**Signup**
1. `POST /auth/signup` → `auth_service.signup` → hash password, insert `User`, insert
   `Workspace`, insert `WorkspaceMember(role=owner)`, all in one DB transaction.
2. `issue_token_pair` → insert `RefreshToken`, encode access JWT.
3. Route sets the refresh cookie, returns `AuthResponse` with the access token in the
   body.

**Refresh rotation**
1. Client's access token expires; a 401 triggers the frontend's refresh flow (Phase 3
   wires this — `POST /auth/refresh` relies only on the cookie, no body).
2. `auth_service.refresh` hashes the cookie value, loads the `RefreshToken` row.
3. Live → revoke it, issue a new pair, set the new cookie. Already revoked → revoke the
   whole family, 401 (the frontend's refresh call fails, forcing a re-login — the
   correct behavior when a token was replayed).

**Invite-code join**
1. Owner calls `POST /workspaces/{id}/members/invite-code` → `rotate_invite_code`
   overwrites `workspaces.invite_code`, writes an audit-log row, returns the code out
   of band (e.g. shared via Slack — no in-app invite delivery in this phase).
2. Invitee calls `POST /workspaces/join` with the code → `join_by_code` looks up the
   workspace by `invite_code`, inserts a `WorkspaceMember(role=responder)`, writes an
   audit-log row with the *invitee* as actor.

## Edge Cases & Error Handling

| Edge case | Handling |
|---|---|
| Signup with an already-registered email | `ConflictError` (409) from the DB's unique constraint |
| Login with wrong password / nonexistent email / inactive user | Identical `UnauthorizedError("Invalid email or password")` (401) — no user-enumeration signal |
| Refresh cookie missing | `UnauthorizedError` (401) |
| Refresh token hash not found in `refresh_tokens` | `UnauthorizedError` (401) — treated the same as "revoked" from the caller's perspective |
| Refresh token already revoked (reuse) | Revoke the entire token family for that user, `UnauthorizedError` (401) |
| Refresh token past `expires_at` | Treated as invalid — `UnauthorizedError` (401); expired rows aren't proactively deleted in this phase (a cleanup job is a later-phase job-queue concern, not this one's) |
| `/auth/demo` called more than the rate limit allows | `429` |
| No demo workspace exists yet when `/auth/demo` is called | `create_demo_guest` creates a minimal one — never a hard failure |
| Non-member queries any workspace-scoped endpoint | `NotFoundError` (404) via the existing `get_current_workspace` dependency — unchanged from Phase 1 |
| Member (non-owner) calls an owner-only endpoint | `ForbiddenError` (403) via `require_role(OWNER)` |
| Owner tries to demote/remove themself as the workspace's only owner | `ConflictError` (409) — a workspace must always have ≥1 owner |
| Join with an unknown/stale invite code | `NotFoundError` (404) — same signal as "code never existed" |
| Join a workspace the caller is already a member of | `ConflictError` (409) |
