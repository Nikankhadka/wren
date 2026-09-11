import { expect, test } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";

/**
 * W-4: every path that reaches the go-live confirm step supplies the
 * suggested address, and a confirm failure (invalid, reserved, or taken
 * slug) is an actionable field error a retry can recover from.
 *
 * Fully mocked, following the pattern in onboarding-transport.spec.ts:
 * page.route on both `/api/onboarding/state` and `/api/knowledge/records`
 * (the page's mount does Promise.all over both), installed before
 * loginAsTenantAdmin.
 *
 * US-2's refresh half needs the suggestion to change while the page is
 * open. The confirm block and the beat composer are mutually exclusive in
 * the page's render, so nothing on the confirm screen itself can trigger a
 * second state read - the observable moment is the SSE `state` event that
 * opens the confirm step, which carries the freshly recomputed
 * `suggested_slug` with it. The last test drives exactly that: under the old
 * `current || fields.suggested_slug` latch the field would still read the
 * stale mount-time suggestion.
 *
 * US-2's freeze half is structural - `slugDraft` is only ever written by the
 * field's own onChange, and `applyStateFields` writes `suggestedSlug`, never
 * it - and is exercised by the 409 retry below, where a typed address
 * survives a failed confirm.
 */

const BUSINESS_NAME = "Sababa Cafe";
const SUGGESTED_SLUG = "sababa-cafe";

function confirmReadyState(overrides: Record<string, unknown> = {}) {
  return {
    stage: "confirm",
    prompt: "",
    draft: { name: "Nikan", business_name: BUSINESS_NAME },
    completed: false,
    history: [{ role: "assistant", content: "Anything else before you go live?" }],
    input: null,
    can_confirm: true,
    suggested_slug: SUGGESTED_SLUG,
    paused_beat: null,
    ...overrides,
  };
}

const draftRecord = {
  id: "draft-1",
  filename: "notes.txt",
  doc_type: "other",
  status: "draft",
  error: null,
  sections: [{ heading: "Hours", body: "9 to 5, Monday to Friday" }],
  offering_candidates: [],
};

async function mockState(
  page: import("@playwright/test").Page,
  state: Record<string, unknown>,
) {
  await page.route("**/api/onboarding/state", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(state) }),
  );
}

async function mockRecords(
  page: import("@playwright/test").Page,
  records: Record<string, unknown>[],
) {
  await page.route("**/api/knowledge/records", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(records) }),
  );
}

function problemBody(overrides: Record<string, unknown>) {
  return {
    type: "about:blank",
    title: "Error",
    status: 422,
    detail: "One or more fields are invalid.",
    instance: "",
    code: "validation_failed",
    request_id: "req-1",
    errors: [],
    ...overrides,
  };
}

test("the address field is pre-filled from suggested_slug on load", async ({
  page,
  request,
}) => {
  await mockState(page, confirmReadyState());
  await mockRecords(page, []);

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  await expect(page.getByTestId("onboarding-confirm")).toBeVisible();
  await expect(page.getByTestId("onboarding-public-slug")).toHaveValue(SUGGESTED_SLUG);
  await expect(page.getByTestId("onboarding-going-live-as")).toContainText(BUSINESS_NAME);
});

test("saving a knowledge review opens the confirm step with a non-empty address", async ({
  page,
  request,
}) => {
  // can_confirm is already true server-side, but a pending draft forces the
  // client to show the review sheet first (page.tsx's mount handler) - the
  // recorded implementation evidence for this ticket's review-save path.
  await mockState(page, confirmReadyState());
  await mockRecords(page, [draftRecord]);
  // W-11c: onboarding saves go through the batch endpoint now - the response
  // is {published, failed, offering_candidates}, not the single-record shape.
  await page.route("**/api/onboarding/knowledge/batch", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        published: ["draft-1"],
        failed: [],
        offering_candidates: [],
      }),
    }),
  );

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const dialog = page.getByRole("dialog", { name: "Review your information" });
  await expect(dialog).toBeVisible();
  await dialog.getByTestId("onboarding-knowledge-save").click();

  await expect(dialog).toBeHidden();
  await expect(page.getByTestId("onboarding-confirm")).toBeVisible();
  await expect(page.getByTestId("onboarding-public-slug")).toHaveValue(SUGGESTED_SLUG);
});

test("discarding a knowledge review opens the confirm step with a non-empty address", async ({
  page,
  request,
}) => {
  await mockState(page, confirmReadyState());
  await mockRecords(page, [draftRecord]);
  await page.route("**/api/knowledge/records/*", (route) =>
    route.fulfill({ status: 204, body: "" }),
  );

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const dialog = page.getByRole("dialog", { name: "Review your information" });
  await expect(dialog).toBeVisible();
  await dialog.getByTestId("onboarding-knowledge-discard").click();

  await expect(dialog).toBeHidden();
  await expect(page.getByTestId("onboarding-confirm")).toBeVisible();
  await expect(page.getByTestId("onboarding-public-slug")).toHaveValue(SUGGESTED_SLUG);
});

test("a shape violation blocks submission with a field error and issues no confirm request", async ({
  page,
  request,
}) => {
  await mockState(page, confirmReadyState());
  await mockRecords(page, []);

  let confirmRequests = 0;
  await page.route("**/api/onboarding/confirm", (route) => {
    confirmRequests += 1;
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const slug = page.getByTestId("onboarding-public-slug");
  await slug.fill("ab");
  await page.getByTestId("onboarding-confirm").click();

  await expect(slug).toHaveAccessibleDescription(
    "Page address must be at least 3 characters.",
  );
  expect(confirmRequests).toBe(0);
});

test("a reserved-name 422 puts the server's message on the field, without the pydantic prefix", async ({
  page,
  request,
}) => {
  await mockState(page, confirmReadyState());
  await mockRecords(page, []);
  await page.route("**/api/onboarding/confirm", (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify(
        problemBody({
          errors: [
            {
              pointer: "/slug",
              code: "value_error",
              detail: "Value error, that name is reserved; please choose another",
            },
          ],
        }),
      ),
    }),
  );

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);
  await page.getByTestId("onboarding-confirm").click();

  const slug = page.getByTestId("onboarding-public-slug");
  await expect(slug).toHaveAccessibleDescription(
    "that name is reserved; please choose another",
  );
  await expect(slug).not.toHaveAccessibleDescription(/Value error/);
});

test("a 409 taken-slug conflict puts the message on the field, and a retry succeeds", async ({
  page,
  request,
}) => {
  await mockState(page, confirmReadyState());
  await mockRecords(page, []);
  await page.route("**/api/onboarding/confirm", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify(
        problemBody({
          status: 409,
          code: "conflict",
          detail: "That page address is already taken. Choose another.",
          errors: [],
        }),
      ),
    }),
  );

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const slug = page.getByTestId("onboarding-public-slug");
  await slug.fill("cafe-new");
  await page.getByTestId("onboarding-confirm").click();

  await expect(slug).toHaveAccessibleDescription(
    "That page address is already taken. Choose another.",
  );
  // The failure preserved both the entered address and the interview draft -
  // no restart needed, only a different address.
  await expect(slug).toHaveValue("cafe-new");

  // A retry with a different, now-available address succeeds without ever
  // reloading the page or restarting onboarding.
  await page.route("**/api/onboarding/confirm", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ tenant_id: "11111111-1111-1111-1111-111111111111", slug: "cafe-newer" }),
    }),
  );
  await slug.fill("cafe-newer");
  await page.getByTestId("onboarding-confirm").click();

  await expect(page.getByTestId("onboarding-thread")).toContainText(
    "You are live. Your customers get answers now, day or night.",
  );
});

test("the suggestion follows a corrected business name right up to the confirm step", async ({
  page,
  request,
}) => {
  // Mid-interview, with a stale suggestion already prefilled at mount.
  await mockState(
    page,
    confirmReadyState({
      stage: "hours",
      prompt: "What days and hours are you open?",
      draft: { name: "Nikan", business_name: "Sabbaba Cafe" },
      can_confirm: false,
      suggested_slug: "sabbaba-cafe",
      input: {
        kind: "text",
        placeholder: "",
        chips: [],
        mask: null,
        cta_label: null,
        prefix: null,
        suggest_owner_email: false,
      },
    }),
  );
  await mockRecords(page, []);

  // The owner's answer corrects the business name, so the server recomputes
  // `suggested_slug` and sends it back on the same `state` event that opens
  // the confirm step.
  await page.route("**/api/onboarding/message/stream", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: [
        'data: {"type":"reply","text":"Got it - open weekdays."}',
        `data: ${JSON.stringify({
          type: "state",
          stage: "confirm",
          prompt: "",
          draft: { name: "Nikan", business_name: BUSINESS_NAME },
          completed: false,
          input: null,
          can_confirm: true,
          suggested_slug: SUGGESTED_SLUG,
          paused_beat: null,
        })}`,
        'data: {"type":"done"}',
        "",
      ].join("\n\n"),
    }),
  );

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const composer = page.getByTestId("onboarding-composer");
  await composer.getByRole("textbox").fill("Weekdays 9 to 5, and it is Sababa Cafe");
  await composer.getByRole("button", { name: "Send" }).click();

  // The confirm step opens on the refreshed suggestion, not the stale one the
  // page latched at mount. The old `current || fields.suggested_slug` shape
  // would still be showing "sabbaba-cafe" here.
  await expect(page.getByTestId("onboarding-confirm")).toBeVisible();
  await expect(page.getByTestId("onboarding-public-slug")).toHaveValue(SUGGESTED_SLUG);
});
