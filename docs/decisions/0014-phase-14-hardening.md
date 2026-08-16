# ADR 0014: Hardening — A Real Cross-Tenant Test Bug, and a Correct Review Finding Overturned by a Wrong One

## 1. `/auth/refresh` is deliberately excluded from rate limiting

**Context.** The FRD's first draft rate-limited `/auth/login`, `/auth/signup`, and
`/auth/refresh` together, on the theory that all three are "cheap-to-call,
unauthenticated auth endpoints" sharing one threat model. Wiring this up and running
the full backend suite surfaced the real problem: `/auth/refresh` fires automatically
on *every* page load via `AuthProvider`'s boot-time silent-refresh effect (Phase 2), not
just on a deliberate user action — grepping the e2e suite alone found 57+ `page.goto()`
calls, each one a `/auth/refresh` attempt.

**Decision.** Removed `/auth/refresh` from the rate-limited set entirely.
`login_bucket` (capacity 30/60s) now only guards `/auth/login` and `/auth/signup`,
which really are guessable-credential surfaces. `/auth/refresh` isn't brute-forceable
in the first place — it requires an already-valid signed cookie, not a guessable
credential, and Phase 2's single-use rotation + reuse detection already covers the
actual abuse case (a stolen/replayed refresh token). Rate-limiting it would have
throttled ordinary multi-tab and frequent-navigation usage for no real security
benefit. Discovered by running the real backend test suite, not by reasoning about it
in the abstract — the same category of "verify by actually running it" lesson this
project has hit before (ADR 0012 §4).

## 2. `max_request_bytes` must sit *above* `max_upload_bytes`, not below it

**Context.** The request-size-cap middleware's first draft set
`max_request_bytes=2_097_152` (2MB) as "comfortably above any legitimate JSON payload
this API accepts" — a claim that was simply wrong: `max_upload_bytes` (a pre-existing
Phase 5 setting bounding one postmortem field) is 10MB, five times larger. Running the
existing `test_raw_text_over_size_cap_is_rejected` test against the new middleware
failed immediately — a legitimately-sized-but-large postmortem now got a generic 413
from the new outer check before ever reaching the field-level validator that was
supposed to produce a more specific 422.

**Decision.** Corrected `max_request_bytes` to `15_728_640` (15MB) — comfortably above
`max_upload_bytes`, not below it. The two caps are intentionally different in *kind*,
not just size: `max_upload_bytes` bounds one specific field's character count
post-parse; `max_request_bytes` is an outer, pre-parse defense-in-depth boundary
against a request nowhere near legitimate (hundreds of MB), and must never be tighter
than the field-level cap it wraps. This is the second finding in this phase alone
where writing the number down in the FRD first, then implementing and testing against
it, caught a design mistake docs-first work can silently carry — exactly the value of
Step 6 (TEST-BE) actually running against real assertions rather than trusting the
written spec.

## 3. A vacuous test, and a code review finding that was itself wrong

**Context.** The generated tenant-isolation test (FR-09) iterates the FastAPI app's own
route table via `route.original_router.routes` — a non-standard attribute this
project's pinned FastAPI version (0.141.1) exposes, discovered empirically by running
`for r in app.routes: print(type(r).__name__, ...)` directly against the real app and
finding `_IncludedRouter` wrapper objects, not the flattened `APIRoute` list a more
familiar older FastAPI version would produce. The generator's own path templates
(matching what that traversal returns) never carried the `/api/v1` prefix
`app.main.create_app()` actually mounts every router under. The test asserted
`response.status_code == 404` for a cross-tenant request — which passed, but for the
wrong reason: an unprefixed path matches no route at all, so Starlette's own generic
"not found" fires regardless of whether the app's real `workspace_id` filtering works.
Every one of the seven parametrized cases was passing vacuously.

**Decision.** The code-reviewer sub-agent caught this correctly (missing `/api/v1`
prefix on the actual HTTP call) and fixed it by prefixing the request path and
asserting on the app's own `error.code == "not_found"` envelope, not just the status
code, so a future missing-prefix regression can't silently pass on a generic 404
again. The *same* review pass also raised a second BLOCKING finding claiming
`original_router` doesn't exist on this FastAPI version at all and that the route
generator always returns zero routes — directly contradicted by rerunning the exact
traversal against the live app a second time (58 real routes found, matching the first
discovery). That finding was dismissed as a false positive, not applied. Both things
are true at once: a real bug from *not* empirically verifying enough during
implementation, caught by a review pass that itself made a claim not empirically
verified against this project's actual pinned dependency versions. The fix for the
first came from checking the code against reality; the correct response to the second
came from doing the same thing to the review comment itself, rather than
"fixing" working code because a review said to.
