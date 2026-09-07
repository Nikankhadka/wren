"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ChatBubble, type ChatRole } from "@/components/ui/ChatBubble";
import { Chip } from "@/components/ui/Chip";
import { StreamingText } from "@/components/ui/StreamingText";
import { CitationChip, type Citation } from "@/components/ui/CitationChip";
import { QuoteCard, type QuotePayload } from "@/components/ui/QuoteCard";
import { EscalationBanner } from "@/components/ui/EscalationBanner";
import { PROGRESS_LABELS, parseChatStreamEvent, type ProgressStage } from "@/lib/chat-events";
import { customerOpening } from "@/lib/greeting";

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
 * T-011/T-032: the interactive half of the customer surface. The branded
 * shell/suspended/not-found states stay in page.tsx (server-resolved, T-005)
 * - this component owns the actual conversation once the shell has decided
 * the tenant is active. No EventSource (POST bodies aren't supported by
 * it) - SSE is parsed by hand from a fetch ReadableStream.
 */
export function CustomerChat({
  slug,
  displayName,
  greeting,
  starterQuestions,
  composerRef,
}: {
  slug: string;
  displayName: string;
  greeting: string | null;
  starterQuestions: string[];
  /** Filled with a function that puts text in the composer, for a parent whose
   * own buttons open this chat with a question already typed. Seeding is an
   * event, so it is a call rather than a prop: a prop would have to be turned
   * back into one, and the obvious way to do that - remounting on a new value
   * - is exactly what throws away the conversation it was opened from. */
  composerRef?: RefObject<((text: string) => void) | null>;
}) {
  // W-9 US-8: the assistant says what it is first, in words the tenant does not
  // own. A configured welcome follows it, minus anything that would say hello a
  // second time.
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", text: customerOpening(displayName, greeting) },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  // C-5 split one flag in two. `escalated` means a tenant limit ended the
  // conversation - the only case that locks the composer. `handoffSeen` means
  // the assistant asked a human to look at something, which is a notification,
  // not a stop: the chat stays live and only the human-reply poll starts.
  const [escalated, setEscalated] = useState(false);
  const [handoffSeen, setHandoffSeen] = useState(false);
  // Which agent stage is running right now, for the live region below. Null
  // between turns; the backend sends one of these per graph node.
  const [stage, setStage] = useState<ProgressStage | null>(null);
  // Starter chips only make sense before the customer has said anything -
  // hidden the moment the first real message goes out, never shown again.
  const [showStarters, setShowStarters] = useState(starterQuestions.length > 0);
  const abortRef = useRef<AbortController | null>(null);
  // Cursor for the transcript poll: the created_at of the newest message we
  // have already fetched. Starts undefined so the first poll fetches the whole
  // tail once, then narrows each tick.
  const pollCursor = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!composerRef) return;
    composerRef.current = setInput;
    return () => {
      composerRef.current = null;
    };
  }, [composerRef]);

  // T-031/C-5: once a topic has been handed to a human, that human may reply
  // (the escalations resolve flow inserts a human_agent message). No push
  // channel exists, so poll the public transcript endpoint and append what
  // arrives. Polling starts on a handoff or a limit stop and runs until
  // unmount; it never runs on a tab that has neither, which keeps it off the
  // backend's back.
  useEffect(() => {
    if (!(handoffSeen || escalated) || !conversationId) return;

    let cancelled = false;

    async function poll() {
      const params = new URLSearchParams({ slug });
      if (pollCursor.current) params.set("after", pollCursor.current);
      try {
        const res = await fetch(
          `${API_URL}/api/chat/${conversationId}/messages?${params.toString()}`
        );
        if (!res.ok || cancelled) return;
        const incoming = (await res.json()) as PublicMessage[];
        if (cancelled || incoming.length === 0) return;
        pollCursor.current = incoming[incoming.length - 1]?.created_at ?? pollCursor.current;
        // Only a human's reply. C-5 keeps the conversation open, so the
        // customer's own messages and the assistant's answers keep being
        // persisted while this poll runs - taking everything would render each
        // of them a second time. A human reply is the one thing this client
        // cannot learn about any other way, and it is all the poll is for.
        const replies = incoming.filter((m) => m.role === "human_agent");
        if (replies.length === 0) return;
        setMessages((prev) => {
          // Dedupe by role + content (the transcript carries no ids the
          // streamed messages share). Applied on every tick, not just the
          // first: a page that restored history already shows earlier replies,
          // and two identical human replies in one thread are far less likely
          // than the double-render this prevents.
          const shown = new Set(prev.map((m) => `${m.role}\0${m.text}`));
          const additions = replies
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
  }, [handoffSeen, escalated, conversationId, slug]);

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
    setStage(null);
    setInput("");
    setShowStarters(false);
    setMessages((prev) => [
      ...prev,
      { role: "customer", text: trimmed },
      { role: "assistant", text: "", streaming: true },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug, conversation_id: conversationId, message: trimmed }),
        signal: controller.signal,
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
          // A malformed or partial SSE frame parses to null; skip it and keep
          // reading rather than abort the in-progress stream.
          const event = parseChatStreamEvent(raw.slice("data: ".length));
          if (!event) continue;

          switch (event.type) {
            case "conversation":
              setConversationId(event.conversation_id);
              break;
            case "citations":
              updateLastAssistant(() => ({ citations: event.citations }));
              break;
            case "quote":
              updateLastAssistant(() => ({ quote: event.quote }));
              break;
            case "progress":
              setStage(event.stage);
              break;
            case "redraft":
              // The backend's price gate rejected the streamed draft and is
              // streaming a replacement - clear the rejected text.
              updateLastAssistant(() => ({ text: "" }));
              break;
            case "token":
              updateLastAssistant((last) => ({ text: last.text + event.text }));
              break;
            case "refusal":
              updateLastAssistant(() => ({ text: event.text }));
              break;
            case "handoff":
              // A human was notified. Nothing about the chat changes.
              setHandoffSeen(true);
              break;
            case "escalated":
              setEscalated(true);
              break;
            case "error":
              // The backend failed mid-stream and said so on the wire. Without
              // this the bubble would sit in "streaming" forever - show the
              // same retry affordance a network failure gets below.
              updateLastAssistant(() => ({
                text: "Something went wrong just then. Try again?",
                error: true,
                streaming: false,
              }));
              break;
            case "done":
              updateLastAssistant(() => ({ streaming: false }));
              break;
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        // Customer-initiated stop. Keep whatever text streamed in, but a stop
        // before the first token would otherwise leave an empty bubble behind
        // forever - drop it instead of just marking it done.
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === "assistant" && last.text === "") {
            return prev.slice(0, -1);
          }
          const next = [...prev];
          if (last) next[next.length - 1] = { ...last, streaming: false };
          return next;
        });
      } else {
        updateLastAssistant(() => ({
          text: "Something went wrong just then. Try again?",
          error: true,
          streaming: false,
        }));
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
      setStage(null);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  function handleStop() {
    abortRef.current?.abort();
  }

  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4 sm:px-6">
        {messages.map((message, index) => (
          <ChatBubble key={index} role={message.role} senderLabel={`${displayName} staff`}>
            <StreamingText
              streaming={message.streaming ?? false}
              pending={message.streaming === true && message.text === ""}
            >
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
        {showStarters ? (
          <div className="flex flex-wrap gap-2 pl-1">
            {starterQuestions.map((question, index) => (
              <Chip
                key={index}
                label={question}
                dashed
                data-testid={`starter-${index}`}
                onClick={() => void send(question)}
              />
            ))}
          </div>
        ) : null}
      </div>

      {escalated ? (
        <EscalationBanner />
      ) : (
        <form
          onSubmit={handleSubmit}
          className="flex shrink-0 flex-col gap-2 border-t border-border p-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
        >
          {/* Mounted unconditionally (only the text toggles) - screen readers
              reliably announce content changes inside an existing live
              region, but often miss one that appears and disappears with its
              content in the same render. */}
          <p className="h-4 text-footnote text-text-secondary" aria-live="polite">
            {busy ? (stage ? PROGRESS_LABELS[stage] : "Answering…") : ""}
          </p>
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Input
                label="Message"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={busy}
                autoFocus
              />
            </div>
            {busy ? (
              <Button type="button" variant="secondary" onClick={handleStop}>
                Stop
              </Button>
            ) : (
              <Button type="submit" loading={busy}>
                Send
              </Button>
            )}
          </div>
        </form>
      )}
    </>
  );
}
