# Skill: e2e-tester — Step 11 of Every Module

## Purpose
Run Playwright end-to-end tests that exercise the full module flow through the browser
against a real running stack. This is the final quality gate before push.

## Stack for e2e
Uses docker-compose.test.yml — an isolated Postgres + seeded API + dev frontend.
Never runs against the development database.

## Invocation
Say: "Spawning e2e-tester sub-agent for module: <name>"

## Setup
```bash
# Start isolated test stack
docker compose -f docker-compose.test.yml up -d --wait

# Confirm all services healthy
docker compose -f docker-compose.test.yml ps
# api-test must show "healthy"
# web-test must be running
```

## Running e2e tests
```bash
cd e2e
npm run test -- --project=chromium
```

Pass criteria: 0 failed tests. Flaky tests must be fixed, not skipped.

## What e2e tests must cover per module

### Module has a user-facing flow (any frontend screen):
Write or extend tests in `e2e/tests/<module-name>.spec.ts` covering:
1. Happy path — the full user journey documented in the PRD acceptance criteria
2. Auth boundary — unauthenticated request is rejected (redirect to login)
3. RBAC boundary — a viewer cannot perform owner/responder actions
4. Error state — what the user sees when the API returns an error
5. Empty state — what the user sees with no data

### Module has no frontend (pure backend e2e):
Write API-level e2e tests in `e2e/tests/<module-name>-api.spec.ts` using
Playwright's `request` fixture:
1. Happy path through the endpoint sequence
2. Auth enforcement
3. Cross-tenant isolation (request as workspace-A user for workspace-B resource)

### E2e tests do not exist yet for this module:
Write them now. Do not skip Step 11 because tests are missing — write the tests,
then run them.

## E2e test file template

```typescript
// e2e/tests/<module-name>.spec.ts
import { test, expect } from "@playwright/test";

const BASE = process.env.E2E_FRONTEND_URL ?? "http://localhost:5174";
const API  = process.env.E2E_BASE_URL     ?? "http://localhost:8001";

test.describe("<Module Name>", () => {
  test.beforeEach(async ({ page }) => {
    // Log in as test user
    await page.goto(`${BASE}/login`);
    await page.fill('[data-testid="email"]', process.env.E2E_TEST_USER_EMAIL!);
    await page.fill('[data-testid="password"]', process.env.E2E_TEST_USER_PASSWORD!);
    await page.click('[data-testid="login-submit"]');
    await expect(page).toHaveURL(/dashboard/);
  });

  test("happy path — <describe the journey>", async ({ page }) => {
    // Steps matching PRD acceptance criteria
  });

  test("unauthenticated access is rejected", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto(`${BASE}/<protected-route>`);
    await expect(page).toHaveURL(/login/);
  });

  test("viewer cannot perform write actions", async ({ page, request }) => {
    // Switch to viewer session and attempt a mutation
  });
});
```

## After e2e run
```bash
# Tear down test stack
docker compose -f docker-compose.test.yml down
```

## Output format
```
## E2E Test Run: <Module Name>
Stack: docker-compose.test.yml
Browser: chromium

### Result: PASS | FAIL

### Test summary
N passed, N failed, N skipped (skipped must be 0)

### Failed tests (if any)
Test: <name>
Error: <message>
Screenshot: <path if captured>
Fix required: <what to fix in application code>

### Next step
PASS  → proceed to Step 12 (push)
FAIL  → fix application code, re-run from Step 11
```
