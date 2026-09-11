import { expect, test } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SLUG = "bytefix";

/**
 * C-6 (and C-5's deferred E2E): the owner steps into a live conversation, talks
 * to the customer directly, and hands it back.
 *
 * Deliberately model-free. The behaviour under test is who is allowed to speak
 * and whether the customer's composer stays live - reproducing it through a
 * real escalation would need the assistant to decide to escalate, which is not
 * deterministic on a free-tier provider. The customer's side is driven through
 * the public API the browser itself calls.
 */
test("staff take a conversation over, reply, and hand it back", async ({ page, request }) => {
  // A customer conversation, created exactly as the chat surface creates one.
  const opened = await request.post(`${API_URL}/api/chat`, {
    data: { slug: SLUG, message: "Can I speak to a person please?" },
  });
  expect(opened.ok()).toBeTruthy();
  const conversationId = /"conversation_id": ?"([0-9a-f-]{36})"/.exec(await opened.text())?.[1];
  expect(conversationId).toBeTruthy();

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);
  await page.goto(`/chats/${conversationId}`);

  // The assistant has it, and the screen says so rather than leaving the owner
  // to infer it from which controls are showing.
  await expect(page.getByTestId("thread-status")).toHaveText("Handling");
  await expect(page.getByText("Can I speak to a person please?")).toBeVisible();

  await page.getByTestId("take-over").click();
  // Stepping in never asks - it only adds the owner, it takes nothing away.
  await expect(page.getByTestId("confirm-accept")).toHaveCount(0);
  await expect(page.getByTestId("thread-status")).toHaveText("You're replying");
  // The stamp lands in the transcript, so the history says who was speaking.
  await expect(page.getByText("You took over this conversation")).toBeVisible();

  const reply = "Hi, it's Sam from ByteFix - happy to help.";
  await page.getByRole("textbox").fill(reply);
  await page.keyboard.press("Enter");
  await expect(page.getByText(reply)).toBeVisible();

  // The customer's side: still open, and the human's words reached it.
  const transcript = await request.get(
    `${API_URL}/api/chat/${conversationId}/messages?slug=${SLUG}`
  );
  const messages = (await transcript.json()) as { role: string; content: string }[];
  expect(messages.some((m) => m.role === "human_agent" && m.content === reply)).toBeTruthy();

  // While a human has it, the assistant stays quiet - and does not end the chat.
  const whileHeld = await request.post(`${API_URL}/api/chat`, {
    data: { slug: SLUG, conversation_id: conversationId, message: "thanks!" },
  });
  const events = await whileHeld.text();
  expect(events).toContain('"type": "handoff"');
  expect(events).not.toContain('"type": "escalated"');

  // The customer never reads the words "human agent" - the reply is labelled
  // with a person at the business. The owner-side transcript viewer renders the
  // same bubble in the same customer perspective, so it is where this is
  // checkable without driving a live model to a handoff.
  await page.goto(`/conversations/${conversationId}`);
  await expect(page.getByText(reply)).toBeVisible();
  await expect(page.getByText("Business staff")).toBeVisible();
  await expect(page.getByText("Human agent")).toHaveCount(0);

  await page.goto(`/chats/${conversationId}`);
  await page.getByTestId("hand-back").click();
  await page.getByTestId("confirm-accept").click();
  await expect(page.getByTestId("thread-status")).toHaveText("Handling");
  await expect(page.getByText("Handed back to Agencx")).toBeVisible();
});
