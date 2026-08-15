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

async function loginViaUi(page: import("@playwright/test").Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correcthorse123");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
}

test.describe("Observability, Settings, API Keys (Phase 13)", () => {
  // Same cold-start hazard ADR 0007 §5 documents for search/incidents -- the ingest
  // webhook drives the identical embedding pipeline a session-authenticated postmortem
  // create does, so it pays the same first-call tax in a freshly built api-test
  // container.
  test.beforeAll(async () => {
    test.setTimeout(90_000);
    const warmup = await signupViaApi("E2E Warmup User", uniqueEmail("e2e-observability-warmup"));
    await warmup.ctx.get(`/api/v1/workspaces/${warmup.workspaceId}/search`, {
      headers: { Authorization: `Bearer ${warmup.accessToken}` },
      params: { q: "warm up the embedding model", mode: "vector" },
    });
    await warmup.ctx.dispose();
  });

  test("the full API key checkpoint: create, ingest via webhook, revoke, then 401", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    const ownerEmail = uniqueEmail("e2e-apikey-owner");
    const owner = await signupViaApi("API Key Owner", ownerEmail);
    await owner.ctx.dispose();

    await loginViaUi(page, ownerEmail);
    await page.goto("/settings");

    await page.getByLabel("New API key name").fill("e2e webhook key");
    await page.getByRole("button", { name: "Create key" }).click();

    // Scoped to .first() -- once the list refetches, the new key's own row also shows
    // a truncated `<code>{prefix}…</code>` starting with the same "hs_" text, and the
    // full-value banner renders above that list in the DOM.
    const rawKeyLocator = page.locator("code").filter({ hasText: /^hs_/ }).first();
    await expect(rawKeyLocator).toBeVisible();
    const rawKey = (await rawKeyLocator.textContent())?.trim();
    expect(rawKey).toMatch(/^hs_/);

    await page.getByRole("button", { name: "Done, I've copied it" }).click();

    // The webhook is an external caller's path -- authenticated by the raw key alone,
    // never a session cookie/bearer token.
    const webhookCtx = await playwrightRequest.newContext({ baseURL: API_BASE_URL });
    const ingestResp = await webhookCtx.post("/api/v1/ingest/postmortem", {
      headers: { "X-API-Key": rawKey as string },
      data: {
        title: "E2E webhook ingest — cache eviction storm",
        raw_text:
          "Summary: a bulk cache eviction triggered a thundering herd against the primary DB.",
      },
    });
    expect(ingestResp.ok(), await ingestResp.text()).toBeTruthy();
    const postmortem = await ingestResp.json();
    expect(postmortem.title).toBe("E2E webhook ingest — cache eviction storm");

    // Confirm it really landed in this workspace's corpus, not just a 201 in a vacuum.
    await page.goto("/knowledge-base");
    await expect(page.getByText("E2E webhook ingest — cache eviction storm")).toBeVisible({
      timeout: 30_000,
    });

    await page.goto("/settings");
    await expect(page.getByText("e2e webhook key")).toBeVisible();
    await page.getByRole("button", { name: "Revoke" }).click();
    await expect(page.getByText("revoked")).toBeVisible();

    const revokedResp = await webhookCtx.post("/api/v1/ingest/postmortem", {
      headers: { "X-API-Key": rawKey as string },
      data: { title: "should never be created", raw_text: "the key is revoked by now" },
    });
    expect(revokedResp.status()).toBe(401);
    await webhookCtx.dispose();
  });

  test("Settings walkthrough: invite, role change, and the audit log reflects both", async ({
    page,
  }) => {
    test.setTimeout(45_000);
    const ownerEmail = uniqueEmail("e2e-settings-owner");
    const memberEmail = uniqueEmail("e2e-settings-member");
    const owner = await signupViaApi("Settings Owner", ownerEmail);
    const member = await signupViaApi("Settings Member", memberEmail);
    await member.ctx.dispose();

    await loginViaUi(page, ownerEmail);
    await page.goto("/settings");

    await page.getByRole("button", { name: "Rotate invite code" }).click();
    const codeLocator = page.locator("code").first();
    await expect(codeLocator).toBeVisible();
    const code = (await codeLocator.textContent())?.trim();

    const joinResp = await owner.ctx.post("/api/v1/workspaces/join", {
      headers: { Authorization: `Bearer ${member.accessToken}` },
      data: { code },
    });
    expect(joinResp.ok(), await joinResp.text()).toBeTruthy();
    await owner.ctx.dispose();

    await page.reload();
    await expect(page.getByText("Settings Member")).toBeVisible({ timeout: 15_000 });
    await page
      .getByRole("combobox", { name: "Role for Settings Member" })
      .selectOption("responder");

    await page.goto("/audit-log");
    await expect(page.getByText("workspace.member_role_changed")).toBeVisible({
      timeout: 15_000,
    });

    // F12 smoke: the Agent Runs page loads for an owner even with no runs yet in this
    // freshly created workspace -- not part of this journey's main assertion, just
    // confirming the route composes cleanly end to end.
    await page.goto("/agent-runs");
    await expect(page.getByRole("heading", { name: "Agent Runs" })).toBeVisible();
  });
});
