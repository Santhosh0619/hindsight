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

async function createService(
  owner: SignupResult,
  name: string,
  tier: number,
  teamId: string | null = null
): Promise<string> {
  const resp = await owner.ctx.post(
    `/api/v1/workspaces/${owner.workspaceId}/catalog/services`,
    {
      headers: { Authorization: `Bearer ${owner.accessToken}` },
      data: { name, tier, team_id: teamId },
    }
  );
  expect(resp.ok(), await resp.text()).toBeTruthy();
  return (await resp.json()).id as string;
}

async function createEdge(
  owner: SignupResult,
  fromServiceId: string,
  toServiceId: string
): Promise<void> {
  const resp = await owner.ctx.post(`/api/v1/workspaces/${owner.workspaceId}/catalog/edges`, {
    headers: { Authorization: `Bearer ${owner.accessToken}` },
    data: {
      from_service_id: fromServiceId,
      to_service_id: toServiceId,
      kind: "calls",
      criticality: "hard",
    },
  });
  expect(resp.ok(), await resp.text()).toBeTruthy();
}

test.describe("Service Map, Knowledge Base, Dashboard", () => {
  // api-test's first-ever embed() call cold-loads sentence-transformers/torch in a
  // freshly built container -- same one-time cost documented in ADR 0007 §5. Warmed
  // once here so the ingest test's own timing reflects the feature, not the
  // interpreter's cold start.
  test.beforeAll(async () => {
    test.setTimeout(90_000);
    const warmup = await signupViaApi("E2E Warmup User", uniqueEmail("e2e-p10-warmup"));
    await warmup.ctx.get(`/api/v1/workspaces/${warmup.workspaceId}/search`, {
      headers: { Authorization: `Bearer ${warmup.accessToken}` },
      params: { q: "warm up the embedding model", mode: "vector" },
    });
    await warmup.ctx.dispose();
  });

  test("ingesting a postmortem through the UI shows it indexed, then in the detail view", async ({
    page,
  }) => {
    const email = uniqueEmail("e2e-kb-owner");
    await page.goto("/signup");
    await page.getByLabel("Full name").fill("KB Owner");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Sign up" }).click();
    await page.getByRole("button", { name: "Start empty" }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    await page.goto("/knowledge-base");
    await expect(page.getByText("No postmortems yet")).toBeVisible();

    await page.getByRole("button", { name: "New postmortem" }).click();
    await page.getByLabel("Title").fill("checkout-api pool exhaustion");
    await page
      .getByLabel("Document")
      .fill(
        "Summary:\nThe checkout-api service returned a spike of 500 errors after a bad " +
          "deploy exhausted its outbound connection pool.\n"
      );
    await page.getByRole("button", { name: "Ingest" }).click();

    await expect(page.getByText("Indexed. It now appears in the table.")).toBeVisible({
      timeout: 20_000,
    });
    await page.getByRole("button", { name: "Close" }).first().click();

    await page.getByText("checkout-api pool exhaustion").click();
    await expect(page).toHaveURL(/\/knowledge-base\/[0-9a-f-]+$/);
    await expect(page.getByRole("heading", { name: "Document" })).toBeVisible();
    await expect(page.getByText(/bad deploy exhausted/)).toBeVisible();
    await expect(page.getByText("No facts extracted yet.")).toBeVisible();
  });

  test("the service map renders seeded services and a selected node's blast radius", async ({
    page,
  }) => {
    const email = uniqueEmail("e2e-map-owner");
    const owner = await signupViaApi("Map Owner", email);

    const upstreamId = await createService(owner, "checkout-api", 1);
    const downstreamId = await createService(owner, "payments-svc", 2);
    await createEdge(owner, upstreamId, downstreamId);
    await owner.ctx.dispose();

    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    await page.goto("/service-map");
    await expect(page.getByRole("button", { name: "checkout-api" })).toBeVisible();
    await expect(page.getByRole("button", { name: "payments-svc" })).toBeVisible();

    await page.getByRole("button", { name: "checkout-api" }).click();
    await expect(page.getByRole("heading", { name: "checkout-api" })).toBeVisible();
    await expect(page.getByText("Tier 1")).toBeVisible();
    // The side panel resolves the real blast radius for the clicked service --
    // payments-svc is one hop downstream.
    await expect(
      page.getByText("payments-svc", { exact: true }).last()
    ).toBeVisible();
  });

  test("the dashboard reflects real corpus and catalog state", async ({ page }) => {
    const email = uniqueEmail("e2e-dashboard-owner");
    const owner = await signupViaApi("Dashboard Owner", email);
    await createService(owner, "checkout-api", 1);
    await owner.ctx.dispose();

    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    await expect(page.getByText("Open incidents")).toBeVisible();
    await expect(page.getByText("Corpus size")).toBeVisible();
    await expect(page.getByText("Most fragile services")).toBeVisible();
    // A brand-new workspace with a service but no incidents still lists it,
    // scored at zero rather than being filtered out.
    await expect(page.getByRole("cell", { name: "checkout-api" })).toBeVisible();
  });

  test("a viewer can browse all three screens but cannot see New postmortem", async ({
    page,
  }) => {
    const ownerEmail = uniqueEmail("e2e-p10-rbac-owner");
    const memberEmail = uniqueEmail("e2e-p10-rbac-member");

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

    await page.goto("/service-map");
    await expect(page.getByText("No services yet")).toBeVisible();

    await page.goto("/knowledge-base");
    await expect(page.getByText("No postmortems yet")).toBeVisible();
    await expect(page.getByRole("button", { name: "New postmortem" })).not.toBeVisible();

    await page.goto("/dashboard");
    await expect(page.getByText("Open incidents")).toBeVisible();
  });

  test("unauthenticated visits redirect to /login", async ({ page }) => {
    await page.context().clearCookies();

    await page.goto("/service-map");
    await expect(page).toHaveURL(/\/login/);

    await page.goto("/knowledge-base");
    await expect(page).toHaveURL(/\/login/);

    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });
});
