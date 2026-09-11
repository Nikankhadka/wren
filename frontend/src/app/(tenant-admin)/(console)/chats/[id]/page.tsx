"use client";

import { use, useEffect, useRef, useState } from "react";
import { ChatBubble } from "@/components/ui/ChatBubble";
import { CommandPill } from "@/components/ui/CommandPill";
import { ScreenTopbar } from "@/components/ui/ScreenTopbar";
import { StructuredResponse } from "@/components/ui/StructuredResponse";
import { apiFetch, ApiError } from "@/lib/api";
import type { ConversationDetail } from "@/lib/api-schemas";
import { clockTime, customerLabel } from "@/lib/format";

/**
 * C-6 Chats thread: the owner reads a conversation, steps into it, and hands it
 * back.
 *
 * The two states this screen exists to make obvious are "my assistant is
 * handling this" and "I am replying". Both are named in the topbar rather than
 * implied by which controls are visible, because an owner who is unsure which
 * one is true will not type - and a message sent while the assistant is still
 * answering puts two voices in one thread.
 *
 * Ported from agencx-prototype-v6.html's `renderThreadScreen` / `alexTko` /
 * `alexHbk`: `thr-st` status, the take-over and hand-back pills, and the
 * symmetrical stamps in the transcript. Mounted chrome-free until E-1.
 */

// The customer's own replies arrive while the owner is reading, and there is no
// push channel - same constraint, same answer, as the customer surface.
const POLL_INTERVAL_MS = 4000;

export default function ChatThreadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Bumped after a takeover, handback or reply so the transcript refetches
  // immediately instead of waiting out the poll interval.
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const next = await apiFetch<ConversationDetail>(`/api/conversations/${id}`);
        if (cancelled) return;
        setDetail(next);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.detail : "Could not load this conversation.");
      }
    }

    void load();
    const timer = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [id, reloadToken]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [detail?.messages.length]);

  const takenOver = detail?.status === "human";
  // A conversation a tenant limit ended is not one to step into - the cap is
  // the point. The pill is simply absent rather than present-and-failing.
  const stopped = detail?.status === "escalated" || detail?.status === "closed";

  async function act(path: string, body?: unknown) {
    setWorking(true);
    setError(null);
    try {
      await apiFetch(`/api/conversations/${id}/${path}`, {
        method: "POST",
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      setReloadToken((token) => token + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "That didn't go through.");
    } finally {
      setWorking(false);
    }
  }

  // Built from the route id, not the response, so the title is right on first
  // paint instead of flashing a placeholder while the detail request is out.
  const customerName = customerLabel(detail?.customer_ref, id);

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg">
      <ScreenTopbar title={customerName} backHref="/chats" />
      <p
        data-testid="thread-status"
        className={`px-5 pb-2 text-footnote ${takenOver ? "text-text-secondary" : "text-accent-active"}`}
      >
        {stopped ? "Stopped" : takenOver ? "You're replying" : "Handling"}
      </p>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto px-5 pb-4">
        {detail?.messages.map((message) => (
          <div key={message.id} className="flex flex-col gap-1">
            <ChatBubble role={message.role as never} perspective="operator">
              {message.role === "system" ? (
                // The prototype's `thr-pill`: a centred stamp with the time it
                // happened, so the history says who was speaking and from when.
                <span className="inline-block rounded-full bg-bubble-in px-3.5 py-1">
                  {message.content}
                  <span className="text-text-tertiary"> · {clockTime(message.created_at)}</span>
                </span>
              ) : (
                message.content
              )}
            </ChatBubble>
            <div className="max-w-[85%] self-end">
              <StructuredResponse response={message.metadata.response} />
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error ? <p className="px-5 pb-2 text-footnote text-danger">{error}</p> : null}

      {stopped ? null : (
        <div className="shrink-0 border-t border-hairline px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3">
          <div className="mb-2.5 text-center">
            <button
              type="button"
              disabled={working}
              data-testid={takenOver ? "hand-back" : "take-over"}
              onClick={() => void act(takenOver ? "handback" : "takeover")}
              className="inline-block rounded-full bg-accent-subtle px-3.5 py-1.5 text-chip font-medium text-accent-active disabled:opacity-50"
            >
              {takenOver ? "Hand back to Agencx" : "Take over this conversation"}
            </button>
          </div>
          {takenOver ? (
            <CommandPill
              value={draft}
              onChange={setDraft}
              placeholder="Type a message…"
              disabled={working}
              onSubmit={(text) => {
                setDraft("");
                void act("reply", { message: text });
              }}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}
