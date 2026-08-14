import { test, expect, request as playwrightRequest, APIRequestContext } from "@playwright/test";

const API_BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:8001";
const INDEX_TIMEOUT_MS = 30_000;
const INDEX_POLL_INTERVAL_MS = 500;

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 100000)}@example.com`;
}

interface SignupResult {
  ctx: APIRequestContext;
  accessToken: string;
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
  const workspaceId: string = (await meResp.json()).memberships[0].workspace_id;

  return { ctx, accessToken, workspaceId };
}

// Ingestion (redact/screen/chunk/embed/index) runs on worker-test with no LLM
// configured, so it completes without a key; the follow-on extract_postmortem job
// (which needs an LLM to link a postmortem to a service) dead-letters harmlessly.
// Polls the status endpoint rather than sleeping a fixed amount, since worker
// throughput isn't guaranteed under CI load.
async function ingestAndWaitForIndex(
  ctx: APIRequestContext,
  token: string,
  workspaceId: string,
  rawText: string
): Promise<string> {
  const createResp = await ctx.post(`/api/v1/workspaces/${workspaceId}/postmortems`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { title: "e2e fixture postmortem", raw_text: rawText },
  });
  expect(createResp.ok(), await createResp.text()).toBeTruthy();
  const postmortemId: string = (await createResp.json()).id;

  const deadline = Date.now() + INDEX_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const statusResp = await ctx.get(
      `/api/v1/workspaces/${workspaceId}/postmortems/${postmortemId}/status`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    const body = await statusResp.json();
    if (body.status === "indexed") return postmortemId;
    if (body.status === "failed") {
      throw new Error(`postmortem ${postmortemId} failed to ingest: ${body.failure_reason}`);
    }
    await new Promise((resolve) => setTimeout(resolve, INDEX_POLL_INTERVAL_MS));
  }
  throw new Error(`postmortem ${postmortemId} did not reach "indexed" within ${INDEX_TIMEOUT_MS}ms`);
}

test.describe("Search (F10)", () => {
  // api-test is a freshly built container -- its first-ever embed() call cold-loads
  // sentence-transformers/torch into the process, which can take well past a UI
  // assertion's default timeout. Warm it once here so every test below is timing the
  // feature itself, not this stack's one-time cold start.
  test.beforeAll(async () => {
    const { ctx, accessToken, workspaceId } = await signupViaApi(
      "E2E Warmup User",
      uniqueEmail("e2e-search-warmup")
    );
    await ctx.get(`/api/v1/workspaces/${workspaceId}/search`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { q: "warm up the embedding model", mode: "vector" },
    });
    await ctx.dispose();
  });

  test("hybrid search surfaces vector and keyword signals with source-attribution chips", async ({
    page,
  }) => {
    const email = uniqueEmail("e2e-search");
    const { ctx, accessToken, workspaceId } = await signupViaApi("E2E Search User", email);

    // Two fixtures exercising the two retrievers this stack can produce without a
    // configured LLM key -- graph mode's service-linkage requires the extraction
    // agent (Phase 6), which needs a real provider; that path is already covered by
    // backend pytest's DB-level fixtures (test_retrieval.py, test_search_api.py) and
    // gets a live-LLM e2e pass once the user adds a key, per the standing plan.
    await ingestAndWaitForIndex(
      ctx,
      accessToken,
      workspaceId,
      "Summary:\nOur database ran completely out of available connections during peak traffic.\n"
    );
    await ingestAndWaitForIndex(
      ctx,
      accessToken,
      workspaceId,
      "Summary:\nORA-12520: TNS listener could not find available handler.\n"
    );
    await ctx.dispose();

    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto("/search");
    await expect(page.getByRole("tab", { name: "Hybrid" })).toHaveAttribute(
      "aria-selected",
      "true"
    );

    // AC-1: vocabulary absent from the target text still retrieves it (mode=vector).
    await page.getByRole("tab", { name: "Vector" }).click();
    await page.getByLabel("Search query").fill("connection pool exhausted");
    await expect(page.getByText(/database ran completely out of available connections/)).toBeVisible();
    await expect(page.getByText(/vector #\d/)).toBeVisible();

    // AC-2: an exact error code retrieves the postmortem containing it (mode=keyword).
    await page.getByRole("tab", { name: "Keyword" }).click();
    await page.getByLabel("Search query").fill("ORA-12520");
    await expect(page.getByText(/TNS listener could not find available handler/)).toBeVisible();
    await expect(page.getByText(/keyword #\d/)).toBeVisible();

    // AC-4: the two modes return visibly different result sets for the same signal --
    // re-querying the vector fixture's own phrase in vector mode must not also surface
    // the unrelated keyword fixture (their embeddings sit well past the distance
    // threshold; only sharing the literal "ORA-12520" string would pull it in).
    await page.getByRole("tab", { name: "Vector" }).click();
    await page.getByLabel("Search query").fill("connection pool exhausted");
    await expect(page.getByText(/database ran completely out of available connections/)).toBeVisible();
    await expect(page.getByText(/TNS listener could not find available handler/)).not.toBeVisible();
  });

  test("an unmatched query shows the no-results empty state", async ({ page }) => {
    const email = uniqueEmail("e2e-search-empty");
    const { ctx, accessToken, workspaceId } = await signupViaApi("E2E Empty Search User", email);
    await ingestAndWaitForIndex(
      ctx,
      accessToken,
      workspaceId,
      "Summary:\nA routine deploy completed with no incident.\n"
    );
    await ctx.dispose();

    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto("/search");
    // A real but topically unrelated phrase -- keeps the vector-distance assertion
    // honest (a nonsense/gibberish token could embed unpredictably close to
    // anything) while still sharing no lexemes with the fixture's tsv content.
    await page.getByLabel("Search query").fill("weather forecast for coastal fishing tomorrow");

    await expect(page.getByText("No results")).toBeVisible();
  });

  test("search never returns another workspace's postmortems", async ({ page }) => {
    const ownerA = uniqueEmail("e2e-search-a");
    const ownerB = uniqueEmail("e2e-search-b");
    const a = await signupViaApi("Workspace A Owner", ownerA);
    const b = await signupViaApi("Workspace B Owner", ownerB);

    await ingestAndWaitForIndex(
      a.ctx,
      a.accessToken,
      a.workspaceId,
      "Summary:\nA distinctive cross-tenant search fixture phrase for workspace A.\n"
    );
    await a.ctx.dispose();
    await b.ctx.dispose();

    await page.goto("/login");
    await page.getByLabel("Email").fill(ownerB);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto("/search");
    await page.getByLabel("Search query").fill("distinctive cross-tenant search fixture phrase");

    await expect(page.getByText("No results")).toBeVisible();
  });

  test("an unauthenticated visit to /search redirects to /login", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/search");

    await expect(page).toHaveURL(/\/login/);
  });
});
