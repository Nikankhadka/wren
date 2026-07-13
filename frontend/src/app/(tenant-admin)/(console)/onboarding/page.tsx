"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ChatBubble } from "@/components/ui/ChatBubble";
import { apiFetch, ApiError } from "@/lib/api";

interface OnboardingStateResponse {
  stage: string;
  prompt: string;
  draft: Record<string, Record<string, unknown>>;
  completed: boolean;
}

interface Message {
  role: "assistant" | "customer";
  text: string;
}

const STAGE_LABELS: Record<string, string> = {
  identity: "About your business",
  tone: "Voice and tone",
  services: "Services & products",
  pricing_rules: "Pricing rules",
  escalation_threshold: "Escalation threshold",
  knowledge_prompt: "Knowledge",
  confirm: "Review & confirm",
};

/**
 * T-006: the Copilot onboarding chat (Surface-2). Chat pane on the left,
 * live captured-summary panel on the right, per frontend.md 7.2. The
 * transcript itself isn't persisted server-side (only stage + draft are) -
 * a refresh resumes at the right stage but replays only its current prompt,
 * not the full prior conversation.
 */
export default function OnboardingPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [stage, setStage] = useState<string>("identity");
  const [draft, setDraft] = useState<Record<string, Record<string, unknown>>>({});
  const [completed, setCompleted] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    apiFetch<OnboardingStateResponse>("/api/onboarding/state")
      .then((state) => {
        setStage(state.stage);
        setDraft(state.draft);
        setCompleted(state.completed);
        if (!state.completed) {
          setMessages([{ role: "assistant", text: state.prompt }]);
        }
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Failed to load onboarding"))
      .finally(() => setLoaded(true));
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!input.trim()) return;
    setError(null);
    setBusy(true);
    const text = input;
    setInput("");
    setMessages((prev) => [...prev, { role: "customer", text }]);
    try {
      const state = await apiFetch<OnboardingStateResponse>("/api/onboarding/message", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      setStage(state.stage);
      setDraft(state.draft);
      setMessages((prev) => [...prev, { role: "assistant", text: state.prompt }]);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    setError(null);
    setBusy(true);
    try {
      await apiFetch("/api/onboarding/confirm", { method: "POST" });
      setCompleted(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!loaded) {
    return <main className="flex flex-1 items-center justify-center p-8" />;
  }

  return (
    <main className="flex min-h-screen flex-col gap-6 p-8 lg:flex-row">
      <section className="flex flex-1 flex-col rounded-lg border border-border bg-surface p-6">
        <h1 className="text-title-2 font-semibold text-text">Onboarding</h1>
        <p className="mt-1 text-body-sm text-text-secondary">
          Answer a few questions and your assistant will be ready to go live.
        </p>

        <div className="mt-6 flex flex-1 flex-col gap-3 overflow-y-auto">
          {completed ? (
            <ChatBubble role="system">You&apos;re live! Onboarding is complete.</ChatBubble>
          ) : (
            messages.map((message, index) => (
              <ChatBubble key={index} role={message.role}>
                {message.text}
              </ChatBubble>
            ))
          )}
        </div>

        {!completed && stage !== "confirm" ? (
          <form onSubmit={handleSubmit} className="mt-6 flex gap-2">
            <div className="flex-1">
              <Input
                label="Your reply"
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
        ) : null}

        {!completed && stage === "confirm" ? (
          <div className="mt-6">
            <Button onClick={handleConfirm} loading={busy}>
              Confirm &amp; go live
            </Button>
          </div>
        ) : null}

        {error ? <p className="mt-3 text-footnote text-danger">{error}</p> : null}
      </section>

      <aside className="w-full rounded-lg border border-border bg-surface p-6 lg:w-80">
        <h2 className="text-title-3 font-semibold text-text">Captured so far</h2>
        <ul className="mt-4 flex flex-col gap-3">
          {Object.entries(STAGE_LABELS)
            .filter(([key]) => key !== "knowledge_prompt" && key !== "confirm")
            .map(([key, label]) => (
              <li key={key} className="text-body-sm">
                <span className="font-medium text-text">{label}</span>
                <p className="text-text-secondary">
                  {draft[key] ? JSON.stringify(draft[key]) : "Not captured yet"}
                </p>
              </li>
            ))}
        </ul>
      </aside>
    </main>
  );
}
