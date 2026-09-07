import { expect, test } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";

// In the containerized e2e runner the backend itself fetches this URL, and
// localhost:3000 inside that container is not the frontend (F-3) - compose
// points E2E_SITE_URL at the frontend service over the compose network.
const SITE_URL =
  process.env.E2E_SITE_URL ?? "http://localhost:3000/fixtures/example-business.html";
const EDITED = "We fix phones and laptops on the north side, e2e.";

/**
 * O-3 Settings > Knowledge: an owner adds a source, reads back what we made of
 * it, and saves it. The draft gate is the point - nothing answers a customer
 * until the owner has seen the text and said yes.
 */
test("a pasted link is read back as sections, then saved", async ({
  page,
  request,
}) => {
  // The read-back is the model's work on a really-fetched page, nothing
  // stubbed, so with no provider there is nothing to wait for - skip rather
  // than time out. The Makefile derives E2E_LLM from backend/.env.
  test.skip(
    !process.env.E2E_LLM,
    "no LLM provider configured (set LLM_API_KEY in backend/.env) - this spec drives the real URL ingest",
  );

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  // Relative, like every other spec: since D22 there is one origin, so the
  // session the login helper established is simply still here.
  await page.goto("/business/details");
  await expect(page.getByRole("heading", { name: "Settings" })).toHaveCount(0);
  await page.getByText("Knowledge", { exact: true }).click();
  await page.waitForURL("**/business/details/knowledge");

  await page.getByTestId("knowledge-url-input").fill(SITE_URL);
  await page.getByTestId("knowledge-url-submit").click();

  // The review sheet opens with the page processed into readable sections.
  const sheet = page.getByRole("dialog", { name: "Read this back" });
  await expect(sheet).toBeVisible({ timeout: 90_000 });
  await sheet.getByRole("button", { name: "Edit" }).first().click();
  const sections = sheet.getByRole("textbox", { name: /details/ });
  await expect(sections.first()).toBeVisible();
  const before = await sections.first().inputValue();
  expect(before.length).toBeGreaterThan(0);

  // The owner's correction is what gets saved - this is a text they edit.
  await sections.first().fill(EDITED);
  await page.getByTestId("knowledge-save").click();

  await expect(page.getByTestId("knowledge-save")).toHaveCount(0, { timeout: 30_000 });

  // The saved text is now what the assistant knows, and it says so. Scoped to
  // this record: the demo tenant may already carry others.
  const saved = page.locator("article").filter({ hasText: EDITED });
  await expect(saved).toBeVisible({ timeout: 30_000 });
  await saved.getByText("View reviewed document").click();
  await expect(saved.getByText(EDITED)).toBeVisible();
  await expect(saved.getByText("Answering from this")).toBeVisible();
  await expect(page.getByTestId("knowledge-error")).toHaveCount(0);

  // Removing it takes it back out of what the assistant knows.
  await saved.getByTestId("knowledge-remove").click();
  await expect(page.locator("article").filter({ hasText: EDITED })).toHaveCount(
    0,
    {
      timeout: 30_000,
    },
  );
});
