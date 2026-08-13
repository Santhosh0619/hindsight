# FRD: Frontend Foundation

## API Endpoints (Backend)

None new — this phase only *consumes* Phase 2's existing endpoints:
`POST /api/v1/auth/{signup,login,refresh,logout,demo}`, `GET /api/v1/auth/me`,
`POST /api/v1/workspaces`, `GET /api/v1/workspaces`.

## React Components (Frontend)

### `src/lib/api.ts`
- Typed `apiFetch<T>(path, options)` wrapping `fetch`, always `credentials: "include"`
  (so the httpOnly refresh cookie rides along), `Content-Type: application/json` for
  bodies, and an `Authorization: Bearer <accessToken>` header sourced from
  `lib/auth.tsx`'s in-memory token.
- On a `401` response (except from `/auth/refresh` and `/auth/login` themselves, to
  avoid infinite loops): calls a module-level `refreshAccessToken()` once, then retries
  the original request with the new token. If a refresh is already in flight, concurrent
  callers await the same in-flight promise instead of each starting their own — the
  request-queueing FR-05 requires.
- Throws a typed `ApiError{status, code, message, detail}` parsed from the backend's
  `{"error": {...}}` envelope (`app/core/errors.py`'s shape) on any non-2xx after the
  retry.
- `API_BASE_URL` from `import.meta.env.VITE_API_URL`, defaulting to
  `http://localhost:8000` — never hardcoded inline at each call site.

### `src/lib/auth.tsx`
- `AuthProvider` — holds `{ user: UserOut | null, accessToken: string | null, status:
  "loading" | "authenticated" | "unauthenticated" }` in React state (never persisted —
  a hard refresh always re-derives it).
- On mount, calls `POST /auth/refresh` once (silent, via the httpOnly cookie) to attempt
  to restore a session before rendering children — this is FR-04's "no visible flash"
  mechanism: `status` starts `"loading"` and the app shows a full-page skeleton until it
  resolves to `"authenticated"` or `"unauthenticated"`.
- `useAuth()` hook exposing `{ user, status, login, signup, logout, loginAsDemo }`.
- `<ProtectedRoute>` — renders `<Outlet />` if `status === "authenticated"`, redirects to
  `/login` (preserving the attempted path in `state`) if `"unauthenticated"`, renders a
  loading skeleton while `"loading"`.
- `useRequireRole(...roles)` — reads the caller's role for the *current* workspace from
  `user`'s memberships (once a workspace is selected) and returns a boolean; used by UI
  to hide/disable write actions per FR-07.

### `src/components/layout/AppShell.tsx`
- Sidebar listing all 14 screens (plan.md §6): route + label + icon; the current
  workspace name/switcher above the list; a user menu (email, logout) below.
- Screens without a real page yet route to `<StubPage phase={N} name="..." />`
  (`components/layout/EmptyState.tsx` variant) instead of 404ing.
- `PageHeader{title, description?, actions?}` — consistent per-page header used by every
  future screen.
- `ErrorBoundary` — catches render errors in any routed page, shows a recoverable error
  state instead of a blank white screen.
- `LoadingSkeleton` — generic block/line skeleton, used both by the auth bootstrap and
  by later data-fetching pages.

### `src/components/ui/`
shadcn/ui primitives (`button`, `input`, `card`, `dialog`, `dropdown-menu`, `avatar`,
`skeleton`, `separator`) plus this project's own small set built on top of them:
`SeverityBadge` (sev1–sev4 color-coded), `ConfidenceBadge` (percentage + color band),
`StatusPill` (generic colored status text), `MetricCard` (label + big number, for
future dashboard use), `Timestamp` (relative + absolute on hover, monospace).

### Pages
- `src/pages/Landing.tsx` (F1) — problem statement, two CTAs (signup / try demo).
- `src/pages/Login.tsx`, `src/pages/Signup.tsx` (F2) — forms, inline validation errors
  surfaced from `ApiError`, a demo-entry link.
- `src/pages/Onboarding.tsx` (F3) — two-choice screen. Signup already creates the
  user's personal workspace (Phase 2), so neither choice calls `POST /workspaces` —
  that would leave the user with a redundant second workspace. "Start empty" simply
  proceeds to the dashboard with the existing workspace; "Seed with demo data" is
  present but disabled with a "coming in Phase 11" label (honest about the gap, not a
  dead button that silently does nothing).
- `src/pages/StubRoute.tsx` — generic `EmptyState` for every F4–F14 route, reused by
  `routes.tsx`'s route table.

### `src/routes.tsx`
Central route table: public (`/`, `/login`, `/signup`), protected-wrapped (everything
else), mapping each of plan.md §6's F4–F14 screens to a stub, and F1–F3 to their real
pages.

## Data Model Changes

None — no new backend tables. `src/lib/types.ts` mirrors Phase 2's response shapes
(`UserOut`, `MembershipOut`, `WorkspaceOut`) as TypeScript interfaces, hand-kept in sync
with the Pydantic schemas (no codegen in this phase — see NFR Constraints).

## Internal Architecture

- `src/lib/queryClient.ts` — a single `QueryClient` instance (React Query), default
  `staleTime`/`retry` tuned for a mostly-static app at this phase (no live data yet).
- `src/lib/theme.ts` — the dark-first design tokens (colors, the one accent, spacing
  scale) as CSS custom properties, consumed by `tailwind.config.ts` rather than
  hardcoded Tailwind defaults — plan.md's "do not use default shadcn colors unchanged"
  requirement.
- `src/main.tsx` — mounts `<QueryClientProvider>` → `<AuthProvider>` →
  `<BrowserRouter>` → `<App />`, in that order (auth must be ready before routes decide
  what to render).

## Dependencies

Depends entirely on Phase 2's auth/workspace API surface (unchanged by this phase).
Every later frontend phase (F4–F14) depends on this phase's `AppShell`, `lib/api.ts`,
`lib/auth.tsx`, and `routes.tsx`.

## Sequence Flows

**App boot (any URL, cold load)**
1. `main.tsx` mounts; `AuthProvider` fires `POST /auth/refresh` immediately.
2. While pending: `status="loading"`, `<ProtectedRoute>` renders `LoadingSkeleton`.
3. Refresh succeeds → `GET /auth/me` → `status="authenticated"`, `user` populated,
   routes render normally. Refresh fails (401, no cookie) → `status="unauthenticated"`,
   protected routes redirect to `/login`.

**Signup → onboarding → shell**
1. `Signup.tsx` → `POST /auth/signup` → access token held in memory, `user` set.
2. Redirect to `/onboarding`. User already has exactly one (personal) workspace from
   signup, but `Onboarding.tsx` still offers the seed/empty choice once, then redirects
   to the dashboard stub route.
3. `AppShell` renders with the new workspace selected.

**A request racing an expired access token**
1. Two components independently call `apiFetch` around the same time; the access token
   has just expired.
2. Both get `401`. The first caller's `apiFetch` starts `refreshAccessToken()`; the
   second caller's `apiFetch` finds a refresh already in flight and awaits the same
   promise instead of issuing a second `/auth/refresh` call.
3. Both retry their original request once, with the new token.

## Edge Cases & Error Handling

| Edge case | Handling |
|---|---|
| Refresh cookie missing/expired on cold load | `status="unauthenticated"`; no error shown, just routes to `/login` on a protected path |
| `/auth/refresh` itself returns 401 | Not retried again (would loop) — treated as a hard logout |
| Signup with an already-used email | `ApiError` (409) rendered inline on the form, not a toast |
| Login with wrong credentials | Generic "Invalid email or password" inline, matching the backend's own no-enumeration message verbatim |
| A route in plan.md §6 with no page yet | `StubRoute` names the owning phase — never a blank screen or a router 404 |
| Render error in any routed page | `ErrorBoundary` shows a recoverable "Something went wrong" state, not a blank white screen |
| `viewer` role in the shell | Workspace-settings/write entry points hidden via `useRequireRole` — enforced again server-side regardless, per Phase 2 |
