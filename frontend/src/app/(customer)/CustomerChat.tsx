"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ChatBubble, type ChatRole } from "@/components/ui/ChatBubble";
import { StreamingText } from "@/components/ui/StreamingText";
import { CitationChip, type Citation } from "@/components/ui/CitationChip";
import { QuoteCard, type QuotePayload } from "@/components/ui/QuoteCard";
import { EscalationBanner } from "@/components/ui/EscalationBanner";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Message {
  role: ChatRole;
  text: string;
  citations?: Citation[];
  quote?: QuotePayload;
  streaming?: boolean;
  error?: boolean;
}

interface PublicMessage {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

const POLL_INTERVAL_MS = 5000;

function renderWithCitations(text: string, citations: Citation[]): ReactNode {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    const citation = match ? citations.find((c) => c.index === Number(match[1])) : undefined;
    return citation ? <CitationChip key={i} citation={citation} /> : <span key={i}>{part}</span>;
  });
}

/**
 * T-011: the interactive half of the customer surface. The branded
 * shell/suspended/not-found states stay in page.tsx (server-resolved, T-005)
 * - this component owns the actual conversation once the shell has decided
 * the tenant is active. No EventSource (POST bodies aren't supported by
 * it) - SSE is parsed by hand from a fetch ReadableStream.
 */
export function CustomerChat({ slug, displayName }: { slug: string; displayName: string }) {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", text: `Hi! How can I help you with ${displayName} today?` },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [escalated, setEscalated] = useState(false);
  // Cursor for the transcript poll: the created_at of the newest message we
  // have already rendered. Starts undefined so the first poll after escalation
  // fetches the whole tail once, then narrows each tick.
  const pollCursor = useRef<string | undefined>(undefined);

  // T-031: an escalated conversation is terminal for the agent, but a human
  // may still reply (escalations.py's resolve inserts a human_agent message).
  // No push channel exists, so poll the public transcript endpoint while
  // escalated and append anything new. Polling stops the moment we leave the
  // escalated state or unmount (interval cleanup) - it never runs otherwise,
  // which keeps this off the backend's back for non-escalated tabs.
  useEffect(() => {
    if (!escalated || !conversationId) return;

    let cancelled = false;

    async function poll() {
      const params = new URLSearchParams({ slug });
      const isFirstTick = pollCursor.current === undefined;
      if (pollCursor.current) params.set("after", pollCursor.current);
      try {
        const res = await fetch(
          `${API_URL}/api/chat/${conversationId}/messages?${params.toString()}`
        );
        if (!res.ok || cancelled) return;
        const incoming = (await res.json()) as PublicMessage[];
        if (cancelled || incoming.length === 0) return;
        pollCursor.current = incoming[incoming.length - 1]?.created_at ?? pollCursor.current;
        setMessages((prev) => {
          // Only the first tick (no cursor yet) can re-fetch messages already
          // on screen - dedupe those by role + content (no server ids in the
          // streamed transcript). Every later tick is already narrowed by the
          // `after` cursor, so its results are new by construction; deduping
          // them against all history would wrongly drop a legitimate repeat.
          if (!isFirstTick) {
            const additions = incoming.map<Message>((m) => ({
              role: m.role as ChatRole,
              text: m.content,
            }));
            return [...prev, ...additions];
          }
          const shown = new Set(prev.map((m) => `${m.role}\0${m.text}`));
          const additions = incoming
            .filter((m) => !shown.has(`${m.role}\0${m.content}`))
            .map<Message>((m) => ({ role: m.role as ChatRole, text: m.content }));
          return additions.length > 0 ? [...prev, ...additions] : prev;
        });
      } catch {
        // Transient network error - the next tick retries.
      }
    }

    void poll();
    const timer = setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [escalated, conversationId, slug]);

  function updateLastAssistant(update: (last: Message) => Partial<Message>) {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last) next[next.length - 1] = { ...last, ...update(last) };
      return next;
    });
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy || escalated) return;
    setBusy(true);
    setInput("");
    setMessages((prev) => [
      ...prev,
      { role: "customer", text: trimmed },
      { role: "assistant", text: "", streaming: true },
    ]);

    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug, conversation_id: conversationId, message: trimmed }),
      });
      if (!res.ok || !res.body) throw new Error("chat request failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const raw of events) {
          if (!raw.startsWith("data: ")) continue;
          const event = JSON.parse(raw.slice("data: ".length));

          if (event.type === "conversation") {
            setConversationId(event.conversation_id);
          } else if (event.type === "citations") {
            updateLastAssistant(() => ({ citations: event.citations }));
          } else if (event.type === "quote") {
            updateLastAssistant(() => ({ quote: event.quote }));
          } else if (event.type === "redraft") {
            // The backend's price gate rejected the streamed draft and is
            // streaming a replacement - clear the rejected text.
            updateLastAssistant(() => ({ text: "" }));
          } else if (event.type === "token") {
            updateLastAssistant((last) => ({ text: last.text + event.text }));
          } else if (event.type === "refusal") {
            updateLastAssistant(() => ({ text: event.text }));
          } else if (event.type === "escalated") {
            setEscalated(true);
          } else if (event.type === "done") {
            updateLastAssistant(() => ({ streaming: false }));
          }
        }
      }
    } catch {
      updateLastAssistant(() => ({
        text: "Something went wrong reaching the assistant.",
        error: true,
        streaming: false,
      }));
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  return (
    <>
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-6 py-4">
        {messages.map((message, index) => (
          <ChatBubble key={index} role={message.role}>
            <StreamingText streaming={message.streaming ?? false}>
              {renderWithCitations(message.text, message.citations ?? [])}
            </StreamingText>
            {message.quote ? <QuoteCard quote={message.quote} /> : null}
            {message.error ? (
              <button
                type="button"
                onClick={() => void send(messages[index - 1]?.text ?? "")}
                className="mt-1 block text-footnote font-medium text-accent hover:text-accent-hover"
              >
                Retry
              </button>
            ) : null}
          </ChatBubble>
        ))}
      </div>

      {escalated ? (
        <EscalationBanner />
      ) : (
        <form onSubmit={handleSubmit} className="flex items-end gap-2 border-t border-border p-4">
          <div className="flex-1">
            <Input
              label="Message"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
              autoFocus
            />
          </div>
          <Button type="submit" loading={busy}>
            Send
          </Button>
        </form>
      )}
    </>
  );
}
