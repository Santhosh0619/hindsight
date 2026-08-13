# NFR: Frontend Foundation

## Performance

- Vite dev server with HMR for local iteration; production build is a static bundle
  served by nginx (already scaffolded in `frontend/Dockerfile`'s production stage).
- React Query's default `staleTime` is set generously (5 min) at this phase since
  nothing here is genuinely live data yet — later phases override per-query as needed.
- No route-level code splitting yet at this phase's scale (3 real pages + stubs) —
  revisit once F4–F14 add real weight.

## Security

- The access token lives in React state only — never `localStorage`/`sessionStorage`
  (XSS-readable) and never a non-httpOnly cookie. Only the refresh token is a cookie,
  and it's httpOnly (JS can't read it at all), set by the backend in Phase 2.
- `apiFetch` always sends `credentials: "include"` so the refresh cookie rides along
  automatically; the frontend never touches its raw value.
- No secret, API key, or backend URL other than `VITE_API_URL` is embedded in frontend
  code — `VITE_API_URL` itself is a public, non-sensitive value (the API's own origin).
- CORS is already restricted to the frontend's origin by Phase 1's `Settings.cors_origins`
  — this phase doesn't touch that, just confirms `http://localhost:5173` is in the list
  (it is, in `.env.example`).

## Reliability

- `ErrorBoundary` at the route level means one page's render crash doesn't blank the
  whole app.
- The 401-retry-once logic in `apiFetch` explicitly does not retry more than once per
  request (no infinite loop if the refresh itself is failing) and does not intercept
  401s from `/auth/login`/`/auth/refresh` themselves (a wrong password is a real 401,
  not a session-expiry signal).
- `AuthProvider`'s boot-time refresh failing is not an error state — it's the normal
  "not logged in yet" path, handled the same as never having a cookie at all.

## Observability

- No frontend telemetry/error-reporting service in this phase (out of scope, no budget
  for a paid service per plan.md's zero-paid-services rule) — errors caught by
  `ErrorBoundary` are logged to the browser console with enough context to debug
  locally; a real error-tracking integration is a later-phase concern if ever added.

## Testability

- Component tests (Vitest + React Testing Library): `apiFetch`'s 401-retry-and-queue
  behavior (mocked fetch), `AuthProvider`'s three status transitions, `ProtectedRoute`'s
  redirect behavior, form validation/error rendering on Login/Signup.
- No E2E yet — same reasoning as Phases 1–2's ADRs: this phase is *what* Playwright
  will eventually drive, but per Master-Prompt.md's workflow, e2e is written once
  there's a stable UI to test against and the isolated compose stack
  (`docker-compose.test.yml`) can build both `api-test` and `web-test` — this phase is
  what finally makes `web-test` buildable (it needs `frontend/package.json`, which
  didn't exist before now). E2E-tester sub-agent runs after this phase's manual browser
  verification confirms the UI is stable.

## Constraints

- React 18, TypeScript strict (`tsconfig.json` already scaffolded with
  `noUncheckedIndexedAccess`/`noImplicitOverride` — Phase 3 doesn't loosen it), Vite,
  Tailwind, shadcn/ui, React Router, React Query — per plan.md §10/Master-Prompt.md
  Phase 3.
- No hand-rolled `fetch` calls outside `lib/api.ts` anywhere in the codebase — every
  future phase's data fetching goes through it.
- No manual `useState`+`useEffect` data-fetching pattern for server state — React Query
  only, per CLAUDE.md's architecture rules.
- Response-shape types in `lib/types.ts` are hand-written to match Phase 2's Pydantic
  schemas, not generated — no OpenAPI-codegen tool is introduced in this phase (would
  be a reasonable addition later; out of scope now to keep the toolchain minimal).
- Design tokens live in exactly one file (`lib/theme.ts` / the Tailwind config it feeds)
  — no ad-hoc hex colors scattered across components.
