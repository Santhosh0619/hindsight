import { test, expect } from "@playwright/test";

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 100000)}@example.com`;
}

test.describe("Landing (F1)", () => {
  test("states the problem and offers signup + demo", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /solved this incident/i })).toBeVisible();
    await expect(page.getByRole("link", { name: "Sign up" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Try the live demo" })).toBeVisible();
  });

  test("Try the live demo logs in as a demo guest with no signup", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Try the live demo" }).click();

    await expect(page).toHaveURL(/\/dashboard/);
    // Was the /dashboard stub's placeholder text before Phase 10 built the real
    // page; now asserts real Dashboard content renders for a demo guest.
    await expect(page.getByText("Open incidents")).toBeVisible();
  });
});

test.describe("Signup → Onboarding → Dashboard (F2, F3)", () => {
  test("full happy path through the shell", async ({ page }) => {
    const email = uniqueEmail("e2e-signup");

    await page.goto("/signup");
    await page.getByLabel("Full name").fill("E2E Signup User");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Sign up" }).click();

    await expect(page).toHaveURL(/\/onboarding/);
    await expect(page.getByRole("button", { name: "Coming in Phase 11" })).toBeDisabled();

    await page.getByRole("button", { name: "Start empty" }).click();

    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByText(email)).toBeVisible();
  });

  test("duplicate email shows an inline error, not a crash", async ({ page }) => {
    const email = uniqueEmail("e2e-dup");

    await page.goto("/signup");
    await page.getByLabel("Full name").fill("First");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Sign up" }).click();
    await expect(page).toHaveURL(/\/onboarding/);

    await page.goto("/signup");
    await page.getByLabel("Full name").fill("Second");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Sign up" }).click();

    await expect(page.getByText(/already exists/i)).toBeVisible();
    await expect(page).toHaveURL(/\/signup/);
  });
});

test.describe("Session persistence (FR-04)", () => {
  test("a hard reload keeps the user logged in", async ({ page }) => {
    const email = uniqueEmail("e2e-reload");

    await page.goto("/signup");
    await page.getByLabel("Full name").fill("Reload User");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Sign up" }).click();
    await page.getByRole("button", { name: "Start empty" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.reload();

    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByText(email)).toBeVisible();
  });
});

test.describe("Protected routes (FR-08)", () => {
  test("an unauthenticated visit to a protected route redirects to /login", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/incidents");

    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe("Logout", () => {
  test("logging out redirects to /login and ends the session", async ({ page }) => {
    const email = uniqueEmail("e2e-logout");

    await page.goto("/signup");
    await page.getByLabel("Full name").fill("Logout User");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correcthorse123");
    await page.getByRole("button", { name: "Sign up" }).click();
    await page.getByRole("button", { name: "Start empty" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.getByRole("button", { name: new RegExp(email) }).click();
    await page.getByRole("menuitem", { name: "Log out" }).click();

    await expect(page).toHaveURL(/\/login/);

    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });
});
