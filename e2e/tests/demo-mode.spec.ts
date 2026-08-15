import { test, expect } from "@playwright/test";

// The seeded connection_pool_exhaustion incident -- one of the 8 flagship incidents
// seed.py precomputes a real brief for (app/seed/generate_incidents.py). Title is
// exactly what generate_incidents.py's _title_for derives from the scenario's own
// alert text, so this is real fixture data, not an invented fixture of this test's own.
const PRECOMPUTED_INCIDENT_TITLE = "Checkout is throwing 500s, database looks maxed out";

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

test.describe("Demo mode (Phase 11)", () => {
  test("a demo guest lands in a workspace already populated with the seeded corpus", async ({
    page,
  }) => {
    await loginAsDemoGuest(page);

    await expect(page.getByText(/demo workspace.*synthetic data.*read-only/i)).toBeVisible();

    await expect(page.getByText("Open incidents")).toBeVisible();
    await expect(page.getByText("Corpus size")).toBeVisible();
    // A brand-new empty workspace never has a nonzero corpus size -- this is only
    // true against the real seeded 80 postmortems. Exact match -- the demo guest's
    // own randomly-generated email (e.g. "guest-af9394f380d3@...") can otherwise
    // contain "80" as a substring and collide with a loose getByText("80").
    await expect(page.getByText("80", { exact: true })).toBeVisible();

    await page.goto("/knowledge-base");
    await expect(page.getByText("No postmortems yet")).not.toBeVisible();
    // Every one of the 80 seeded postmortems finishes the real ingestion pipeline at
    // seed time, so a real "indexed" status pill confirms actual rows rendered.
    // "indexed" also appears as a <select> filter option earlier in the DOM -- the
    // status pill is the last match, same reasoning as KnowledgeBase.test.tsx.
    await expect(page.getByText("indexed").last()).toBeVisible();

    await page.goto("/service-map");
    await expect(page.getByText("No services yet")).not.toBeVisible();
    // payment-gateway-adapter is one of the two deliberate SPOFs the catalog
    // generator engineered (generate_catalog.py) -- confirms real seeded services
    // render, not a placeholder.
    await expect(page.getByRole("button", { name: "payment-gateway-adapter" })).toBeVisible();
  });

  test("a demo guest opens a precomputed-brief incident and sees real hypotheses and citations", async ({
    page,
  }) => {
    await loginAsDemoGuest(page);

    await page.goto("/incidents");
    await page.getByText(PRECOMPUTED_INCIDENT_TITLE).click();
    await expect(page).toHaveURL(/\/incidents\/[0-9a-f-]+$/, { timeout: 15_000 });

    // Precomputed via the real retriever/correlator nodes at seed time (FRD Gap #4),
    // not generated on page load -- "served from cache" is the real from_cache flag.
    await expect(page.getByText("served from cache")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Hypotheses" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Matched prior incidents" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Blast radius" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Runbook" })).toBeVisible();

    // A demo guest is a VIEWER, but the demo-mode carve-out still lets them see the
    // Generate/Regenerate action -- confirms useCanGenerateBrief actually took effect
    // on this exact screen, not just the nav.
    await expect(page.getByRole("button", { name: "Regenerate brief" })).toBeVisible();
  });

  test("a demo guest can generate a new brief against the real seeded corpus", async ({
    page,
  }) => {
    // Real hybrid retrieval against 80 seeded postmortems; the default 30s test
    // timeout can be tight for that even on an otherwise-idle stack (same reasoning
    // as e2e/tests/incidents.spec.ts's own brief-generation test).
    test.setTimeout(60_000);
    await loginAsDemoGuest(page);

    await expect(page.getByRole("link", { name: "New Incident" })).toBeVisible();
    await page.goto("/incidents/new");
    await expect(page.getByText("Read-only access")).not.toBeVisible();

    await page.getByLabel("Alert text").fill("payment-gateway-adapter calls timing out");
    await page.getByRole("button", { name: "Investigate" }).click();

    await expect(page.getByRole("button", { name: "View incident" })).toBeVisible({
      timeout: 30_000,
    });
    // A freshly generated brief, not the precomputed one -- no cache badge here.
    await expect(page.getByText("served from cache")).not.toBeVisible();
    await expect(page.getByRole("heading", { name: "Feedback" })).toBeVisible();
  });
});
