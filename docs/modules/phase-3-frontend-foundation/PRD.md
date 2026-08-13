# PRD: Frontend Foundation
Phase: 3
Screens: F1 (Landing), F2 (Auth), F3 (Onboarding) from plan.md §6 — plus the shared
app shell, design system, and auth wiring every later screen (F4–F14) builds on.

## Problem

Phase 1/2 built a working backend with no way to reach it from a browser. Every later
frontend phase needs a running React app already wired to the auth API, a design
system, protected routing, and a place to add its own screen — without re-solving
"how do I stay logged in" or "what does a button look like" each time.

## Actors

- An unauthenticated visitor on the landing page, deciding whether to sign up or try
  the demo.
- A new user going through signup → onboarding.
- A returning, authenticated user navigating the app shell.
- A demo guest, same shell, read-mostly.
- Every later frontend phase (F4–F14), which extends `routes.tsx` and reuses
  `AppShell`/`lib/api.ts`/`lib/auth.tsx` rather than rebuilding them.

## Functional Requirements

FR-01: `GET /` (Landing, F1) states the 2am-postmortem problem from plan.md §2 in the
first screenful, with a "Try the live demo" CTA (no signup) and a "Sign up" CTA.

FR-02: `GET /login`, `GET /signup` (F2) — email/password forms calling
`POST /api/v1/auth/login` / `/signup`; success stores the access token in memory (never
`localStorage`/cookie — that's the refresh token's job) and redirects into the app. A
"Try the demo instead" link calls `POST /api/v1/auth/demo`.

FR-03: On first login after signup, `GET /onboarding` (F3) offers exactly two choices —
"Seed with demo data" or "Start empty" — then redirects to the dashboard route (a stub
until Phase 10). Users who already have a workspace skip onboarding entirely.

FR-04: A reload of any authenticated page keeps the user logged in without a visible
flash of a logged-out state, using the refresh cookie (already httpOnly, set by Phase
2) to silently mint a new access token before the app renders its authenticated view.

FR-05: Every request through the shared API client automatically retries once on a 401
by calling `/auth/refresh`, and concurrent 401s from simultaneously in-flight requests
trigger exactly one refresh call, not one per request.

FR-06: The app shell (`AppShell`) renders a sidebar listing all 14 screens from
plan.md §6, a workspace switcher, and a user menu with logout. Screens not yet built
(F4–F14 beyond this phase) route to a stub page naming which phase builds them, not a
404 or a crash.

FR-07: A `viewer`-role user sees no write-triggering buttons/actions anywhere the shell
renders role-gated UI (this phase: the workspace switcher/settings entry points only —
most write actions don't exist as UI yet until their own phase).

FR-08: Every route except Landing/Login/Signup/Demo-entry requires an authenticated
session; an unauthenticated visit to any protected route redirects to `/login`.

## User Stories

- As a recruiter, I want to understand the problem and try the product in under a
  minute with zero signup friction.
- As a new user, I want signup to drop me straight into a workspace, not an empty
  screen with no next step.
- As any user, I want a page refresh to never log me out unexpectedly.
- As a later-phase frontend author, I want `AppShell`, `lib/api.ts`, and `lib/auth.tsx`
  already solved so my phase only ever adds one route and one page component.

## Out of Scope

- Every screen beyond F1/F2/F3 — F4–F14 are stub routes only, built in their own
  phases.
- Actual demo-data seeding (Phase 11) — "Seed with demo data" calls a real endpoint
  path that doesn't exist yet in the backend; this phase stubs the choice and routes
  through as if empty, documented honestly as a known gap closed by Phase 11.
- Password reset, email verification, OAuth — same reasons as Phase 2's backend scope.
- Any data-fetching screen beyond auth/workspace (no incidents, no search, no graphs).

## Acceptance Criteria

1. In a real browser: signup → onboarding → an authenticated shell with an empty
   dashboard stub, all through the UI, no manual token handling.
2. Refresh the page while authenticated — session survives, no visible flash of a
   logged-out state.
3. Visit a protected route unauthenticated — redirected to `/login`.
4. `tsc --noEmit`, `eslint`, `prettier --check`, `vitest`, and `vite build` all pass
   cleanly.
