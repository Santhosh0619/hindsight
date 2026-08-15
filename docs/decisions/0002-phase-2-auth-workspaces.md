# ADR 0002: Auth & Workspaces — Token Design, Cookie Scoping, and Bugs Found Live

## 1. Refresh rotation + whole-family revocation on reuse

**Context.** A refresh token that's valid indefinitely and reusable is a standing risk:
if one leaks (log line, XSS, a stolen device), it grants access forever. plan.md
requires "rotating refresh tokens" and reuse detection but doesn't specify the
mechanism.

**Decision.** Every successful `/auth/refresh` call revokes the presented token and
issues a brand-new one (`auth_service.refresh`) — a token is single-use by
construction. If a *revoked* token is ever presented again, that's a signal the token
was captured and is being replayed by someone else (the legitimate client already
moved on to the newer token), so the handler revokes every other live `RefreshToken`
row for that `user_id`, not just the one presented. The tradeoff: a legitimate client
that double-fires a refresh call (e.g. two tabs racing) also gets logged out
everywhere. Accepted — a false-positive full logout is a far smaller cost than leaving
a real replay window open, and it's a rare race in practice since the frontend (Phase
3) will queue concurrent refreshes behind a single in-flight request.

## 2. Invite codes are a column on `workspaces`, not a dedicated table

**Context.** Master-Prompt.md's Phase 2 calls for "invite codes" but plan.md §8's data
model has no `invite_codes` table — an oversight in the original plan, not a deliberate
omission.

**Decision.** Added `workspaces.invite_code` (nullable, unique, indexed) via a new
migration rather than a join table. One workspace has at most one *active* code at a
time; rotating overwrites it, immediately invalidating the old one. This is
"single-active-code," not "single-redemption" — anyone holding the current code can
join once (documented explicitly as an accepted scope limit in the PRD/FRD). A
dedicated table would be the right call if codes needed to be per-invitee, expiring, or
independently revocable without affecting other outstanding invites — none of which
this phase's demo-workspace-invite use case needs. Revisit if a later phase (e.g.
per-seat billing) needs those properties.

## 3. Login and refresh failures are message-identical by construction

**Context.** plan.md's own design-review notes and this phase's own NFR both call
for no user-enumeration signal. It's easy to get this right in the code and wrong in
the error *message* (e.g. "no such user" vs "wrong password" leaking through `detail`).

**Decision.** `auth_service.login` has exactly one `UnauthorizedError("Invalid email or
password")` raise site covering "no such user," "wrong password," and "inactive user" —
there's no branch that could accidentally diverge the message between cases, because
there's only one branch. Same shape for `refresh`: "token not found" and "token
expired" are distinguished internally (different log/metric value if that's ever added)
but both surface as a generic 401 to the caller.

## 4. The refresh cookie's `Path` must match where the router is actually mounted

**Context.** `app/api/v1/auth.py` sets the refresh cookie with `path="/auth"` — correct
for the router's own `APIRouter(prefix="/auth")`, but `app/main.py` mounts it under
`app.include_router(auth_router, prefix="/api/v1")`, so the real route is
`/api/v1/auth/refresh`. A cookie's `Path` attribute is a prefix match against the
*request* URL path, not the router's declared prefix — `/auth` does not prefix-match
`/api/v1/auth/refresh`, so the browser (and, correctly, `httpx`'s test client) never
sent the cookie back on any `/api/v1/auth/*` call. Every `ruff`/`mypy`/unit-test pass
was green throughout, because nothing in that layer exercises real HTTP cookie
semantics — this was only caught by an actual `curl` walkthrough of the live endpoint,
which is exactly the kind of bug type checking can't see.

**Decision.** Cookie path is now `/api/v1/auth`, matching the mount point. Documented
here because the next endpoint that sets a cookie under a different mount prefix will
hit the identical trap if `path=` is copied from the router's own prefix instead of the
app's actual mounted path.

## 5. `COOKIE_SECURE` is overridden to `false` inside the test process only

**Context.** `httpx`'s `AsyncClient`, run against `ASGITransport` at `base_url="http://
test"`, enforces cookie `Secure` semantics like a real browser: a `Secure`-flagged
cookie is silently withheld on every subsequent request because the client sees the
connection as plain HTTP, not HTTPS. `Settings.cookie_secure` defaults to `True` (the
correct, required production behavior). Without an override, every automated request
after signup would silently lose the refresh cookie — not a 401 with a clear cause, but
requests quietly proceeding cookie-less, which is a much easier bug to misread as
"the token logic is wrong" than "the test transport isn't actually HTTPS."

**Decision.** `backend/tests/conftest.py` sets `COOKIE_SECURE=false` via
`os.environ.setdefault(...)` before `app.main` is ever imported (required, since
`Settings` is `lru_cache`d and `app.main` builds `app = create_app()` at module import
time). This only affects the test process's own environment — the shipped default and
every other environment (dev, CI's actual runtime config, production) are unaffected.
Alternative rejected: disabling the check in the app itself for local/test — rejected
because that would mean the code path that actually sets `Secure` is never exercised by
type-checking or the request/response cycle at all, and the whole point of catching
issue #4 above was that a real HTTP walk-through catches things unit assertions don't.

## 6. `CursorPage[T]` can only ever wrap a Pydantic-compatible `T`, never an ORM row

**Context.** The first draft of `workspace_service.list_audit_log` returned
`CursorPage[AuditLog]` — `AuditLog` being the SQLAlchemy ORM class, not the
`AuditLogEntryOut` Pydantic schema. `CursorPage` is a Pydantic generic
(`BaseModel, Generic[T]`); subscripting it with a non-Pydantic type forces Pydantic to
try to build a validation schema for that type at the point the generic is
instantiated, which crashed the entire app at import time
(`PydanticSchemaGenerationError: Unable to generate pydantic-core schema for
app.models.workspace.AuditLog`) — every endpoint, not just the audit log, since the
crash happened while `app/main.py`'s module-level `app = create_app()` was being
evaluated.

**Decision.** The service layer now returns a plain `tuple[list[AuditLog], str |
None]` — raw ORM rows plus the next cursor, nothing Pydantic-aware. The route layer
(`app/api/v1/workspaces.py`) does the actual `CursorPage[AuditLogEntryOut]`
construction, mapping each ORM row through `AuditLogEntryOut.model_validate(...)`. The
general rule going forward: `CursorPage[T]` (and any other Pydantic generic) is a
route/schema-layer concern only — service functions return plain Python types (ORM
objects, tuples, dataclasses), and the mapping into a Pydantic response model happens
exactly once, at the boundary that actually needs it.

## 7. Demo-endpoint rate limiting is an in-memory token bucket, not shared state

**Context.** plan.md calls for `/auth/demo` to be "rate-limited by IP" without
specifying a mechanism, and this project deliberately has no Redis (plan.md §7 — one
Postgres, no extra stores).

**Decision.** `app/services/rate_limit.py`'s `TokenBucket` is a plain in-process dict
keyed by client IP — 5 tokens, refilling 1 per 12 minutes. Explicitly documented (NFR
"Reliability") as not shared across worker processes or replicas: the *effective*
limit under N replicas is `5 × N`, not 5. Accepted for this phase/portfolio scale;
Phase 14 owns the project-wide rate-limiting pass (auth endpoints generally, brief
generation) where a DB-backed or shared-cache approach would be reconsidered if it
ever actually mattered at this project's traffic.
