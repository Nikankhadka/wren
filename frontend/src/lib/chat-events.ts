import type { Citation } from "@/components/ui/CitationChip";
import type { QuotePayload } from "@/components/ui/QuoteCard";
import type { CatalogPayload } from "@/components/ui/CatalogCard";
import type { PriceSummaryPayload } from "@/components/ui/PriceSummaryCard";

/**
 * The customer-chat SSE protocol, mirroring the events the backend emits in
 * app/api/chat.py (`_sse`) and the agent nodes' stream writer. Previously every
 * event was accessed off a bare `JSON.parse` as `any`; this discriminated union
 * types each branch so the chat loop can't silently read a wrong field, and the
 * parser below is the one guarded entry point (a malformed or partial frame
 * must never abort an in-progress stream).
 */
/**
 * Which stage of the agent graph is currently running. The backend emits these
 * as fixed machine keys (app/agents/graph.py `_PROGRESS_STAGES`) and never as
 * display text, so all customer-facing copy lives here on the frontend.
 */
export type ProgressStage =
  | "routing"
  | "answering"
  | "quoting"
  | "checking"
  | "escalating";

export type ChatStreamEvent =
  | { type: "conversation"; conversation_id: string }
  | { type: "citations"; citations: Citation[] }
  | { type: "quote"; quote: QuotePayload }
  | { type: "price_summary"; summary: PriceSummaryPayload }
  | { type: "catalog"; catalog: CatalogPayload }
  | { type: "progress"; stage: ProgressStage }
  | { type: "redraft" }
  | { type: "token"; text: string }
  | { type: "refusal"; text: string }
  /**
   * The assistant handed a topic to a human (C-5). The conversation is still
   * open: the composer stays live and the next message gets a full agent turn.
   * The customer only needs a human's reply to be able to arrive, so this
   * starts the transcript poll and nothing else.
   */
  | { type: "handoff" }
  /**
   * The conversation is over - a tenant limit stopped it (daily budget, step
   * cap, turn budget, provider failure). This is the only terminal event, and
   * the only one that locks the composer. Before C-5 the assistant emitted it
   * for ordinary handoffs too, which ended a working session over one question
   * it could not answer.
   */
  | { type: "escalated" }
  | { type: "error"; code: string; detail: string; request_id: string }
  | { type: "done" };

/**
 * Customer-facing label for each stage. A turn runs several LLM calls in series
 * and nothing the model writes may be shown until inspection clears it, so
 * without this the customer stares at an unexplained pause; naming the current
 * stage makes that wait legible rather than making it shorter.
 */
export const PROGRESS_LABELS: Record<ProgressStage, string> = {
  routing: "Understanding your question…",
  answering: "Finding an answer…",
  quoting: "Preparing your quote…",
  checking: "Checking the answer…",
  escalating: "Passing this to the business…",
};

/**
 * Parse one SSE `data:` payload into a typed event, or `null` if it is not
 * valid JSON with a string `type`. Returning `null` (rather than throwing) lets
 * the caller skip a bad frame and keep reading the stream.
 */
export function parseChatStreamEvent(payload: string): ChatStreamEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch {
    return null;
  }
  if (
    parsed !== null &&
    typeof parsed === "object" &&
    typeof (parsed as { type?: unknown }).type === "string"
  ) {
    return parsed as ChatStreamEvent;
  }
  return null;
}
