import { test, expect } from "@playwright/test";

async function loginAsDemoGuest(page: import("@playwright/test").Page): Promise<void> {
  // A distinct X-Forwarded-For per call gives each demo login its own
  // demo_signup_bucket key (app/services/rate_limit.py), isolated from every other
  // test -- and, since it's randomized rather than a small sequential counter, from
  // repeat runs of this same file within the bucket's 12-minute refill window too
  // (a fixed counter collides with itself across reruns while iterating).
  await page.context().setExtraHTTPHeaders({
    "X-Forwarded-For": `203.0.113.${Math.floor(Math.random() * 254) + 1}`,
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Try the live demo" }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
}

test.describe("Evaluation (Phase 12)", () => {
  test("a demo guest sees the seeded vector-mode run's real metrics, ablation table, and case results", async ({
    page,
  }) => {
    await loginAsDemoGuest(page);

    await page.goto("/evaluation");

    // docker-compose.test.yml's api-test runs `evaluation.cli --mode vector` once at
    // startup (after app.seed.seed populates the 20 golden eval cases), so this is a
    // real EvalRun scored against the real 80-postmortem seeded corpus, not a fixture
    // this test invents itself.
    await expect(page.getByRole("heading", { name: "Recall@1" })).toBeVisible();
    await expect(page.getByText(/^\d+%$/).first()).toBeVisible();
    // No LLM key in this build -- groundedness must degrade honestly, never show 0%.
    await expect(page.getByText("no LLM key configured")).toBeVisible();

    // Only vector mode was run at seed time; the other two ablation rows must say so
    // in every column (recall@1, recall@5, MRR) rather than showing blank or zeroed
    // cells -- 2 modes x 3 columns = 6.
    await expect(page.getByRole("button", { name: "Vector only" })).toBeVisible();
    await expect(page.getByText("Vector + BM25", { exact: true })).toBeVisible();
    await expect(page.getByText("not yet run")).toHaveCount(6);

    // 20 real golden eval cases were scored -- the drill-down lists them, failing
    // cases first per the NFR, each with a passed/failed pill.
    const resultRows = page.locator("table").last().locator("tbody tr");
    await expect(resultRows).toHaveCount(20);
    await expect(page.getByText("passed").first()).toBeVisible();
  });

  test("unauthenticated visits redirect to /login", async ({ page }) => {
    await page.context().clearCookies();

    await page.goto("/evaluation");
    await expect(page).toHaveURL(/\/login/);
  });
});
