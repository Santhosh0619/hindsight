# ADR 0003: Frontend Foundation — Auth Race, Tooling Choices, Design Split

## 1. React Router v7, not v6 — a real CVE, not just "use the newer one"

**Context.** plan.md's Phase 3 spec calls for React Router without pinning a major
version. `npm audit` on the initial `^6.26.0` install flagged two moderate CVEs
(open redirect via backslash in `<Link>`/`useNavigate`, arbitrary constructor
injection via `deserializeErrors()`) affecting the entire `6.0.0–7.17.0` range.

**Decision.** Adopted `react-router-dom@^7.18.2` (first patched release) instead of
pinning an old v6. This is a brand-new project with zero existing v6-specific code, so
there was no migration cost to avoid — the declarative API used here (`BrowserRouter`,
`Routes`, `Route`, `Outlet`, `useNavigate`) is unchanged between v6 and v7. Also bumped
`vite`/`vitest`/`@vitejs/plugin-react` to current majors (v8/v4/v6 respectively) for the
same reason: `npm audit` flagged a critical vitest UI-server RCE-class vulnerability
(<3.2.6) and a high-severity Vite path-traversal issue on the versions plan.md's stack
table would have implied. `npm audit` reports zero vulnerabilities on the versions
actually pinned in `package.json`.

## 2. React 18 StrictMode exposed a real refresh-token race, not just dev noise

**Context.** `AuthProvider`'s boot-time effect calls `POST /auth/refresh` once to
silently restore a session from the httpOnly cookie (FR-04). A manual browser
walkthrough (`docker compose up` + Playwright, not just `npm test`) found that a hard
page reload logged the user out — `/auth/refresh` returned 401 and the whole session
was gone, even though the cookie had just been set correctly by signup.

Root cause: React 18's StrictMode double-invokes effects in development, firing two
near-simultaneous `/auth/refresh` calls on every mount. Phase 2's refresh tokens are
single-use with whole-family reuse detection — the first of the two calls legitimately
rotates the token; the second, arriving microseconds later with the now-already-revoked
token, looks identical to a stolen-token replay from the backend's point of view, and
revokes the entire session it just helped create. This is not purely a StrictMode
artifact: two browser tabs reloading within the same narrow window would hit the exact
same race in production, where StrictMode doesn't run at all.

**Decision.** Added a `useRef` guard (`hasBootstrapped`) in `AuthProvider` so the actual
refresh logic runs at most once per app lifetime regardless of how many times the effect
callback itself fires. This fixes the single-tab/single-mount case completely (verified:
reload no longer logs the user out, confirmed via a repeated live browser walkthrough,
not just the fix compiling). The **multi-tab** variant of this race — two independent
tabs each mounting their own `AuthProvider` and refreshing within the same window — is
not fixed by a same-tab ref and is called out here as a known, documented limitation:
the correct general fix is a grace period on the backend's reuse-detection window (treat
a revoked token presented within, say, 5–10 seconds of its own rotation as a benign race
rather than a hard replay signal), which is Phase 2 territory and out of scope for a
frontend-only phase. Flagging it here rather than silently leaving it for whoever hits
it next.

## 3. Vite's dev-server watcher needs polling under this project's Docker setup

**Context.** After editing already-mounted frontend source files, the running `web`
container kept serving stale transformed output — `docker compose exec web cat
src/pages/Landing.tsx` showed the new content, but Vite's dev server (`curl
localhost:5173/src/pages/Landing.tsx`) kept returning the old one. Root cause:
`docker-compose.yml` bind-mounts `./frontend/src` from the Windows host filesystem
(this machine's project lives on `D:`, not inside WSL2's native filesystem). Docker
Desktop's Windows-to-Linux file-sharing bridge doesn't reliably propagate inotify
events for that kind of mount, so Vite's default (event-based) watcher never learns a
file changed and keeps serving its in-memory transform cache — even though the
container's own filesystem view of the file is correct.

**Decision.** Set `server.watch.usePolling = true` (300ms interval) in
`vite.config.ts`. Polling reads file mtimes directly instead of depending on
inotify, so it works regardless of the Windows-bind-mount boundary. Cost is a small,
dev-only amount of CPU; production builds don't run a watcher at all. Verified by
restarting the `web` container (to clear the already-stale cache) and confirming a
subsequent edit was picked up without a manual restart.

## 4. Tailwind v4's CSS-first theming, one token file, oklch palette

**Context.** plan.md requires "a deliberate palette, tokens in one file" and explicitly
forbids using default shadcn colors unchanged.

**Decision.** Used Tailwind v4's `@theme` directive in `src/index.css` (no
`tailwind.config.ts` needed for basic theming) to define the entire palette as CSS
custom properties in oklch — background/foreground/card/muted/border/accent/
destructive/warning/success, plus a second accent stop (`--color-accent-2`) used only
as the far end of gradients, never as a second competing brand color. oklch was chosen
over hsl/rgb because perceptually-uniform lightness makes it far easier to keep
contrast consistent while tuning hue (verified this by eye while designing the palette
— shifting hue at a fixed oklch lightness/chroma reliably keeps text/background
contrast where it needs to be, which isn't true shifting hue in hsl).

## 5. The public marketing surface gets visual presence; the app interior stays calm

**Context.** plan.md's original design direction says "calm and dense, not playful...
this is an operations tool." The initial implementation applied that literally
everywhere, including the landing/auth screens — and it read as flat and generic rather
than calm. Design feedback mid-phase: the public-facing pages (the ones a recruiter
actually sees first) needed real visual presence; the authenticated app interior should
stay exactly as restrained as originally planned.

**Decision.** Split the design language in two, deliberately:
- **Public surface** (Landing, Login, Signup, Onboarding — everything before or during
  auth): a `TechBackground` component — a CSS-only dark base, a faint circuit-grid
  pattern, and two slow-drifting accent-colored glow blobs (`blur-3xl` radial
  gradients) — plus a two-stop accent gradient on the landing headline and
  glass-morphic (`bg-card/70 backdrop-blur-md`) auth cards. Pure CSS/gradients, no
  external image asset — nothing to license, nothing to fetch, nothing that can 404,
  consistent with the project's zero-external-dependency ethos even though this isn't
  a paid-service question.
- **App interior** (`AppShell` and everything behind it): unchanged from plan.md's
  original direction — dense sidebar, restrained single-accent highlights (a left
  border on the active nav item, the "sight" in the wordmark), no glow, no gradient
  text, no background treatment. An operations tool a responder reads at 2am should
  not compete for attention with itself.

This is a considered scope split, not scope creep: the two contexts have different
jobs (first impression vs. daily-use legibility), and plan.md's original guidance was
right for one of them.

## 6. Onboarding doesn't call `POST /workspaces` — signup already created one

**Context.** An earlier draft of this phase's FRD had "Start empty" call
`POST /workspaces`. But Phase 2's `signup` already creates the user's personal
workspace as part of the signup transaction — calling it again from onboarding would
leave the user with two workspaces (their real one plus a redundant "empty" one), which
is confusing, not helpful.

**Decision.** `Onboarding.tsx`'s "Start empty" simply navigates to the dashboard with
the workspace signup already created — no additional API call. "Seed with demo data" is
present but disabled with a "coming in Phase 11" label, honest about the gap rather than
a dead button that silently no-ops.

## 7. FR-07's viewer gating was built but never wired in — caught by code review, not by any check

**Context.** `useRequireRole` existed in `lib/auth.tsx` from the first draft, but
nothing in `AppShell.tsx` actually called it — `ruff`/`tsc`/`eslint` all pass cleanly
on dead, unused-but-exported code, and the manual browser walkthrough that verified
this phase's other acceptance criteria never happened to check with a non-owner
account. The code-reviewer sub-agent caught it (FINDING-001, first review pass) by
reading the FRD's explicit requirement, not by any automated tool.

**Decision.** Wired `useRequireRole("owner", "responder")` into `AppShell` to gate the
Settings (F13) sidebar entry — the one write/admin surface that actually exists in the
shell this phase; every other write action FR-07 describes doesn't have UI yet and
will be gated in the phase that builds it. Added both a Vitest component test
(mocking `useAuth`/`useRequireRole`) and, once e2e was unblocked (§8 below), a full
Playwright test that provisions a real owner + viewer through the API, logs in as each
through the real UI, and asserts the visible difference — the kind of check that would
have caught this gap immediately had it existed from the start.

## 8. E2E is unblocked for auth/workspace/frontend features now, not deferred to Phase 11

**Context.** ADR 0001 §4 deferred all Playwright e2e coverage until Phase 11, because
`docker-compose.test.yml`'s `api-test` hard-required `app.seed.seed` (Phase 11) to
even start. That blocker is real for testing catalog/incident features that need seed
data — but auth, workspaces, and this phase's UI don't need any seed data at all; they
create their own data via signup, exactly like the manual walkthrough already did.
Leaving e2e deferred for two more phases just because a *later* phase's dependency
doesn't exist yet was leaving real, checkable regressions (like §7 above) uncaught.

**Decision.** Guarded `api-test`'s startup command to skip the seed step when
`app.seed.seed` isn't importable yet (`python -c 'import app.seed.seed' 2>/dev/null &&
... || echo '...skipping'`) instead of hard-failing, so the isolated stack can start
today and will pick up real seeding automatically the moment Phase 11 lands — no
further change needed then. Added `e2e/tests/auth-frontend.spec.ts` (Landing, signup →
onboarding → dashboard, duplicate-email error, session persistence across reload,
protected-route redirect, logout) and `e2e/tests/rbac-shell.spec.ts` (provisions an
owner + viewer through the API, verifies §7's gating through the real UI). Catalog/
incident/knowledge-base e2e coverage stays deferred until those features and Phase
11's seed data actually exist — this is a partial unblock, not a full reversal of ADR
0001 §4.

## 9. Three more infrastructure bugs found only by actually running the e2e stack

**Context.** `docker-compose.test.yml` and `frontend/Dockerfile` existed since the
initial setup but had never actually been exercised — `frontend/package.json` didn't
exist until this phase, so `web-test` had never once built successfully before now.
Standing the stack up for real (§8) surfaced three separate, unrelated bugs, each
hiding behind the last:

1. **`web-test` was permanently "unhealthy."** Its healthcheck runs `curl -f
   http://localhost:5173/`, but `node:20-slim` doesn't ship `curl` — the command
   itself failed every single time regardless of whether Vite was actually serving
   correctly (it was). Fixed by installing `curl` in `frontend/Dockerfile`'s base
   stage (matching `backend/Dockerfile`'s existing pattern) and in the production
   (nginx:alpine) stage too, which had the identical latent bug for its own
   healthcheck — not yet hit by anything, but would have been at Phase 18 deploy.
2. **The local `.env` pointed `E2E_FRONTEND_URL`/`E2E_BASE_URL` at the regular dev
   containers (`:5173`/`:8000`) instead of the isolated test stack (`:5174`/`:8001`)**
   — `.env.example` had the correct values all along, but this machine's actual
   `.env` didn't match it. Every e2e test run silently exercised the dev database
   instead of the isolated one until this was caught (by noticing
   `page.evaluate(() => window.location.href)` returned port 5173 when it should
   have been 5174). `.env` is gitignored and personal, so this fix doesn't appear in
   the diff — noted here so a future session hitting the same symptom (tests
   "passing" against the wrong stack, or debug instrumentation that never fires)
   checks this first.
3. **`api-test` had no `CORS_ORIGINS` override**, so it fell back to
   `Settings`'s default (`http://localhost:5173,http://localhost:3000`) — which
   doesn't include `web-test`'s port, 5174. Every browser-side POST (signup, login,
   demo) from a page served at :5174 was silently blocked by CORS; the frontend's
   generic error handling (`err instanceof ApiError ? err.message : "..."`) masked it
   as "Couldn't start a demo session." rather than surfacing the real cause. Fixed by
   setting `CORS_ORIGINS: http://localhost:5174` on `api-test`. Also proactively set
   `COOKIE_SECURE: "false"` on the same service — the identical plain-HTTP-vs-Secure-
   cookie issue from ADR 0002 §5, this time for a real browser instead of `httpx`'s
   test client, which would have silently broken session persistence in e2e the same
   way it broke it in production dev testing before that fix.

None of these three were caused by this phase's application code — they were latent
bugs in test infrastructure nobody had run end-to-end before. Each was root-caused by
directly comparing "what does `curl`/`docker exec cat` show" against "what does the
browser actually receive," the same debugging discipline ADR 0001 and ADR 0002 already
established for this project.

## 10. `pre-push`'s frontend section had never actually run — and had a real bug

**Context.** `.claude/hooks/pre-push`'s frontend section was guarded by `-f
frontend/package.json`, which didn't exist until this phase — so it had been dormant
since the hook was first written, never once executed. The first real run failed
immediately: `npx tsc --noEmit --quiet` — `--quiet` isn't a `tsc` flag at all (that's
an ESLint option that leaked in, presumably copied from the ESLint invocation
elsewhere in the same file). The section also ran natively on the host, the exact
pattern ADR 0001 §5 already fixed for the backend section for the same reasons
(toolchain drift, no need to install anything on the host).

**Decision.** Fixed the same way as the backend section: `docker compose exec web
...` instead of native `npx` calls, starting `db`+`api`+`web` first if not already
running. Also expanded it to run the full local quality bar from
`.claude/skills/test-runner.md`'s frontend spec (`tsc`, `eslint --max-warnings 0`,
`prettier --check`, `vitest run`, `vite build`) rather than just `tsc`+`build` — CI's
own frontend job currently only runs `tsc`/`prettier`/`build` and not `eslint`/
`vitest`, which is a narrower bar than the project's own skill definition calls for;
left as noted here rather than expanding this phase's scope to also fix `ci.yml`.
