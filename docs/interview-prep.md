# Interview Prep — Q&A by Phase

Answers written as the project is built, so they teach the design choices to someone who
did not write the code. See `plan.md` §17 for the full required question list.

---

## Phase 0 — Dependency Verification

**Q: Why does this project have a "Phase 0" before any code, and why does it matter?**

A: Library APIs for fast-moving AI tooling (`pydantic-ai`, `langgraph`) and free-tier LLM
model IDs change on a timescale of months, not years. A plan document written even a few
months earlier can describe an API that no longer exists — for example, this project's
plan assumed `pydantic-ai`'s typed-output parameter was called `result_type` with the
value on `.data`; the installed version (`2.27.1`) actually uses `output_type` and
`.output`. Verifying against the real, installed library before writing a single line of
application code avoids building on a hallucinated or stale API surface, and produces a
committed, dated record (`docs/decisions/0000-dependency-verification.md`) of exactly
what was true when the project was built — useful both for debugging later and for
answering "how do you handle a fast-moving dependency" in an interview.

**Q: What would you do if a library's real API differed from what you'd planned for,
mid-build rather than at Phase 0?**

A: The library wins — adapt the code to match reality and record the deviation in an ADR,
rather than fighting the installed version or pinning to an old one just to match a
document. This is stated explicitly as a hard rule in this project's build process
(Master-Prompt.md's Error Recovery Rules).

**Q: The Gemini free-tier model ID isn't hardcoded anywhere — why does that matter?**

A: Free-tier model availability changes faster than the codebase does — Google moved
Pro-series models to paid-only in April 2026, for instance. Hardcoding a model string
means the whole LLM integration breaks the day that ID is retired, with a failure mode
that's opaque to whoever hits it. Instead the model ID lives in `Settings.llm_model` with
a documented default (`gemini-2.5-flash`, chosen for being non-preview/stable) and a full
environment override, so swapping models is a config change, not a code change. If the
API ever rejects the configured ID, the app surfaces a clear error pointing at AI Studio
rather than silently falling back to a different provider — a silent provider swap would
hide a real operational problem (stale config) behind a working demo.

---

## Phase 1 — Foundation

**Q: Why does `GET /health` return `200` even when the database is unreachable?**

A: So an uptime check or load balancer doesn't need special-case logic to distinguish
"the process crashed" from "the process is fine but a dependency is briefly down." The
handler catches any exception from its `SELECT 1` probe and reports `db_connected:
false` / `status: "degraded"` in the body instead of propagating — the endpoint itself
never fails. `llm_configured` is reported the same honest way: it's `bool(llm_api_key)`,
not a hardcoded `true`, so the response always reflects reality without ever calling out
to an LLM provider to find out.

**Q: Why does a caller who isn't a member of a workspace get 404, not 403, on that
workspace's resources?**

A: 403 confirms the resource exists but you're not allowed to see it — which leaks that
a given `workspace_id` (or later, incident/postmortem ID) is real. 404 is
indistinguishable from "doesn't exist," so probing IDs you don't have access to gives an
attacker no information either way. `get_current_workspace` (`app/core/deps.py`) is the
single place this is enforced, and every route built on top of it inherits the same
behaviour rather than each endpoint author having to remember it.

**Q: Refresh tokens are opaque random strings, not JWTs — why the asymmetry with access
tokens?**

A: Access tokens are JWTs because they're self-contained and verified statelessly on
every request — no DB round-trip needed to check one. Refresh tokens are long-lived and
revocable, so they need server-side state anyway (the `refresh_tokens` table); making
them opaque `secrets.token_urlsafe(48)` values and storing only their SHA-256 hash means
a leaked database row can't be turned back into a usable token — the raw value that
would actually authenticate never touches disk. A JWT refresh token would gain nothing
here and would tempt a design where revocation is checked inconsistently.

**Q: Every enum column uses a `values_callable` helper — what breaks if you remove it?**

A: SQLAlchemy's `Enum` type defaults to persisting the Python member's `.name`
(uppercase, e.g. `QUEUED`) as the Postgres label. Every enum in this codebase is defined
with lowercase `.value`s, and code elsewhere already assumes those lowercase labels —
for example the `jobs` table's partial index predicate is
`WHERE status = 'queued'`. Remove the `values_callable=enum_values` argument and the
migration recreates the enum type with uppercase labels, and the very first query
against it throws `invalid input value for enum job_status: "queued"`. This was caught
during Phase 1's own test pass, before it ever reached a later phase's code — see
`docs/decisions/0001-phase-1-foundation.md`.

**Q: Why is there no Playwright e2e run for Phase 1, when CLAUDE.md says never skip it?**

A: The rule is "never skip it," not "always run the full stack regardless of what
exists." Phase 1 has no frontend and no seed data — `docker-compose.test.yml`'s
`web-test` needs `frontend/package.json` (Phase 3) and `api-test`'s startup command
needs `app.seed.seed` (Phase 11); standing that stack up now would fail on modules this
phase's own PRD explicitly puts out of scope. Per the project's own error-recovery rule,
the deviation is recorded (ADR 0001) and the verification gate that actually fits this
phase — integration tests against the real ASGI app, both health-check branches — is
what runs instead. Playwright resumes the moment there's a user journey to drive through
a browser.

---

## Phase 2 — Auth & Workspaces

**Q: Access and refresh tokens — where are they stored, why, and what's your
revocation story?** (plan.md §17 Q11)

A: The access token is a stateless JWT returned in the response body and never
cookied — the frontend (Phase 3) keeps it in memory. It's self-verifying (HS256,
15-minute default TTL), so most requests need zero DB round-trips to authenticate.
The refresh token is the opposite on purpose: an opaque random value
(`secrets.token_urlsafe(48)`) in an httpOnly, Secure, SameSite=Lax cookie scoped to
`/api/v1/auth`, with only its SHA-256 hash ever persisted (`refresh_tokens.token_hash`).
It has to be stateful, because revocation only works if there's a database row to
revoke — a JWT refresh token would be just as fast to check but couldn't be revoked
before its own expiry without a separate blocklist, which is the same DB dependency
with extra steps. Revocation itself is rotation-based: every refresh call revokes the
token it was given and issues a new one, so a token is single-use. If a *revoked* token
is ever presented again, that's a replay signal — the handler revokes every other live
token for that user, not just the one presented, logging the caller out everywhere
rather than leaving a reuse window open.

**Q: Why do login and refresh return the exact same error message for every failure
case?**

A: Because the alternative leaks information. If "no such user" and "wrong password"
returned different messages, an attacker could enumerate valid emails by watching which
error comes back. `auth_service.login` has a single `UnauthorizedError` raise site
covering "no such user," "wrong password," and "inactive account" — there's no code
path that could accidentally diverge the two, because there's only one path. Same
principle behind `get_current_workspace` returning 404 instead of 403 for a non-member:
a 403 confirms the resource exists; 404 doesn't.

**Q: A workspace must always have at least one owner — where is that enforced, and
what happens if you try to violate it?**

A: `workspace_service._count_owners` is checked in both `change_member_role` (demoting
the last owner) and `remove_member` (removing the last owner) before the mutation
happens, raising `ConflictError` (409) if the count would hit zero. It's checked in the
service layer, not the database — there's no CHECK constraint enforcing "at least one
owner per workspace" at the schema level, because that invariant spans multiple rows
(count members WHERE role='owner') in a way a single-row constraint can't express
cheaply. The tradeoff is honest: this is an application-level invariant, not a
database-level one, so it only holds as long as every write path goes through
`workspace_service`. Nothing in this phase's scope writes `workspace_members` any other
way.

**Q: Why does the demo-guest endpoint rate limit in memory instead of using Redis or a
DB table?**

A: The project has one intentional data store — Postgres — and no Redis (plan.md §7's
graph-database reasoning applies here too: don't add infrastructure until there's a
concrete number that justifies it). An in-memory token bucket keyed by IP is enough to
stop casual abuse of a single-process dev/demo deployment. Its known limitation is
explicit, not hidden: under N replicas the effective limit multiplies by N, since each
process has its own bucket. That's an acceptable, documented tradeoff at this project's
traffic — Phase 14's dedicated rate-limiting pass is where it'd be revisited if it ever
needed to hold under real concurrent load.

**Q: What's a bug in this phase that unit tests and type checking didn't catch, and how
did you find it?**

A: The refresh cookie's `Path` was set to `/auth` — correct for the router's own
`APIRouter(prefix="/auth")` in isolation, but wrong once `app.main` mounts it under
`/api/v1`, making the real path `/api/v1/auth/refresh`. A cookie's `Path` is a prefix
match against the actual request URL, not the router's declared prefix, so the browser
(and `httpx`'s test client, which enforces the same cookie semantics) never sent it
back. `ruff` and `mypy` have no way to know what path a route ends up mounted at, and a
unit test that mocks the HTTP layer wouldn't exercise real cookie-path matching either
— this only surfaced from an actual `curl` walkthrough of the running endpoint. The
lesson generalized into this phase's workflow: cookie/session code gets a live
request-response walkthrough, not just green checks, before being called done.
