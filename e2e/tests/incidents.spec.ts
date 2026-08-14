import { test, expect, request as playwrightRequest } from "@playwright/test";

const API_BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:8001";

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 100000)}@example.com`;
}

interface SignupResult {
  ctx: Awaited<ReturnType<typeof playwrightRequest.newContext>>;
  accessToken: string;
  userId: string;
  workspaceId: string;
}

async function signupViaApi(fullName: string, email: string): Promise<SignupResult> {
  const ctx = await playwrightRequest.newContext({ baseURL: API_BASE_URL });
  const signupResp = await ctx.post("/api/v1/auth/signup", {
    data: { email, password: "correcthorse123", full_name: fullName },
  });
  const signupBody = await signupResp.json();
  const accessToken: string = signupBody.access_token;

  const meResp = await ctx.get("/api/v1/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const meBody = await meResp.json();

  return {
    ctx,
    accessToken,
    userId: meBody.user.id,
    workspaceId: meBody.memberships[0].workspace_id,
  };
}

test.describe("Incidents (F5/F6/F7)", () => {
  // api-test's first-ever embed() call (fired by the retriever node's vector search)
  // cold-loads sentence-transformers/torch in a freshly built container -- the same
  // one-time cost documented in ADR 0007 §5 for Phase 7's search e2e suite. Warmed
  // once here so brief-generation timing below reflects the feature, not the
  // interpreter's cold start.
  test.beforeAll(async () => {
    // A freshly (re)started api-test container can take well past the config's
    // default 30s test timeout to load sentence-transformers into process memory on
    // its very first embed() call, even with the model weights already on disk in
    // the shared model-cache volume -- same root cause as ADR 0007 §5, just not
    // always fast enough to land inside the default hook timeout.
    test.setTimeout(90_000);
    const warmup = await signupViaApi("E2E Warmup User", uniqueEmail("e2e-incidents-warmup"));
    await warmup.ctx.get(`/api/v1/workspaces/${warmup.workspaceId}/search`, {
      headers: { Authorization: `Bearer ${warmup.accessToken}` },
      params: { q: "warm up the embedding model", mode: "vector" },
    });
    await warmup.ctx.dispose();
  });

  test("filing an incident drives a live pipeline trace and renders a brief", async ({
    page,
  }) => {
    // Brief generation does real hybrid retrieval + graph work; the default 30s test
    // timeout can be tight for that even on an otherwise-idle stack.
    test.setTimeout(60_000);
    const email = uniqueEmail("e2e-incident-owner");

    // Deliberately not seeding a postmortem here: ingesting one kicks off
    // worker-test's extract_postmortem job, which retries against the (unconfigured)
    // LLM for up to ~50s before dead-lettering. That job holds the workspace's
    // postmortem/chunk rows busy long enough to stall this incident's own retrieval
    // query for the same span -- a real lock-contention hazard in the ingest ->
    // immediately-investigate path, tracked as a follow-up (see progress.md), not
    // something to work around by padding this test's timeout past a minute.
    // Matched-postmortem/citation rendering is already covered without that hazard
    // by BriefView.test.tsx's mocked-data suite.
    await page.goto("/signup");
    await page.getByLabel("Full name").fill("Incident Owner");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Sign up" }).click();
    await expect(page).toHaveURL(/\/onboarding/);
    await page.getByRole("button", { name: "Start empty" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto("/incidents/new");
    await page.getByLabel("Alert text").fill("checkout-api is returning 500 errors");
    await page.getByRole("button", { name: "Investigate" }).click();

    // Driven by the real SSE stream, not a timer -- every node chip reaches "done"
    // (visible via its latency label) within a generous window that accounts for the
    // warmed-but-still-real embedding/graph work each node does.
    await expect(page.getByText("Briefer")).toBeVisible();
    await expect(page.getByRole("button", { name: "View incident" })).toBeVisible({
      timeout: 30_000,
    });

    // No LLM is configured in this stack (this build's standing environment choice),
    // so the brief is the genuine deterministic-only degradation path, not a canned
    // fixture -- the same badge a real quota-exhausted demo run would show.
    await expect(page.getByText("generated without LLM")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Feedback" })).toBeVisible();
  });

  test("a generated incident appears in the list and its detail page renders the brief", async ({
    page,
  }) => {
    test.setTimeout(45_000);
    const email = uniqueEmail("e2e-incident-list");

    await page.goto("/signup");
    await page.getByLabel("Full name").fill("List Owner");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Sign up" }).click();
    await page.getByRole("button", { name: "Start empty" }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    await page.goto("/incidents/new");
    await page.getByLabel("Alert text").fill("payments-svc connection pool exhausted");
    await page.getByRole("button", { name: "Investigate" }).click();
    await expect(page.getByRole("button", { name: "View incident" })).toBeVisible({
      timeout: 30_000,
    });

    await page.goto("/incidents");
    await expect(
      page.getByText("payments-svc connection pool exhausted")
    ).toBeVisible();

    await page.getByText("payments-svc connection pool exhausted").click();
    await expect(page).toHaveURL(/\/incidents\/[0-9a-f-]+$/, { timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "Feedback" })).toBeVisible();

    // Feedback closes the loop from "the model said so" to real signal for Phase 12.
    await page.getByRole("button", { name: "Helpful", exact: true }).click();
    await expect(page.getByText("Thanks for the feedback.")).toBeVisible();
  });

  test("a viewer cannot see or reach New Incident", async ({ page }) => {
    const ownerEmail = uniqueEmail("e2e-incident-rbac-owner");
    const memberEmail = uniqueEmail("e2e-incident-rbac-member");

    const owner = await signupViaApi("RBAC Owner", ownerEmail);
    const member = await signupViaApi("RBAC Member", memberEmail);

    const inviteResp = await owner.ctx.post(
      `/api/v1/workspaces/${owner.workspaceId}/members/invite-code`,
      { headers: { Authorization: `Bearer ${owner.accessToken}` } }
    );
    const { code } = await inviteResp.json();

    await member.ctx.post("/api/v1/workspaces/join", {
      headers: { Authorization: `Bearer ${member.accessToken}` },
      data: { code },
    });
    await owner.ctx.patch(`/api/v1/workspaces/${owner.workspaceId}/members/${member.userId}`, {
      headers: { Authorization: `Bearer ${owner.accessToken}` },
      data: { role: "viewer" },
    });
    await owner.ctx.dispose();
    await member.ctx.dispose();

    await page.goto("/login");
    await page.getByLabel("Email").fill(memberEmail);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    await expect(page.getByRole("link", { name: "New Incident" })).not.toBeVisible();

    await page.goto("/incidents/new");
    await expect(page.getByText("Read-only access")).toBeVisible();
  });

  test("an unauthenticated visit to /incidents/new redirects to /login", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/incidents/new");

    await expect(page).toHaveURL(/\/login/);
  });
});
