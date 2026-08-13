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
