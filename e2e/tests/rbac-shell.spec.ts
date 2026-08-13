import { test, expect, request as playwrightRequest } from "@playwright/test";

const API_BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:8001";

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 100000)}@example.com`;
}

interface SignupResult {
  accessToken: string;
  userId: string;
  workspaceId: string;
  workspaceName: string;
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
  const membership = meBody.memberships[0];

  await ctx.dispose();
  return {
    accessToken,
    userId: meBody.user.id,
    workspaceId: membership.workspace_id,
    workspaceName: membership.workspace_name,
  };
}

test.describe("RBAC — viewer sees no write entry points (FR-07)", () => {
  test("a viewer-role member doesn't see Settings; the owner does", async ({ page }) => {
    const ownerEmail = uniqueEmail("e2e-owner");
    const memberEmail = uniqueEmail("e2e-member");

    // Set up via the API directly, mirroring what a real invite flow does: owner
    // signs up, rotates an invite code, a second user joins (always as responder per
    // Phase 2), then the owner demotes them to viewer.
    const owner = await signupViaApi("RBAC Owner", ownerEmail);
    const member = await signupViaApi("RBAC Member", memberEmail);

    const ownerCtx = await playwrightRequest.newContext({ baseURL: API_BASE_URL });
    const inviteResp = await ownerCtx.post(
      `/api/v1/workspaces/${owner.workspaceId}/members/invite-code`,
      { headers: { Authorization: `Bearer ${owner.accessToken}` } }
    );
    expect(inviteResp.ok(), await inviteResp.text()).toBeTruthy();
    const { code } = await inviteResp.json();

    const memberCtx = await playwrightRequest.newContext({ baseURL: API_BASE_URL });
    const joinResp = await memberCtx.post("/api/v1/workspaces/join", {
      headers: { Authorization: `Bearer ${member.accessToken}` },
      data: { code },
    });
    expect(joinResp.ok(), await joinResp.text()).toBeTruthy();

    const patchResp = await ownerCtx.patch(
      `/api/v1/workspaces/${owner.workspaceId}/members/${member.userId}`,
      {
        headers: { Authorization: `Bearer ${owner.accessToken}` },
        data: { role: "viewer" },
      }
    );
    expect(patchResp.ok(), await patchResp.text()).toBeTruthy();
    expect((await patchResp.json()).role).toBe("viewer");
    await ownerCtx.dispose();
    await memberCtx.dispose();

    // Log in as the member through the real UI and switch to the workspace they're a
    // viewer in (their default membership, per list_my_workspaces's created_at
    // ordering, happens to already be the owner's workspace here, but switching
    // explicitly keeps the test correct regardless of ordering).
    await page.goto("/login");
    await page.getByLabel("Email").fill(memberEmail);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.getByRole("button", { name: /workspace/i }).click();
    await page.getByRole("menuitem", { name: new RegExp(owner.workspaceName) }).click();

    await expect(page.getByRole("link", { name: "Settings" })).not.toBeVisible();

    // Log in as the owner and confirm Settings IS visible in their own workspace.
    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel("Email").fill(ownerEmail);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await expect(page.getByRole("link", { name: "Settings" })).toBeVisible();
  });
});
