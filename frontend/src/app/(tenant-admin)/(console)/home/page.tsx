"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import type { ConversationSummary } from "@/lib/api-schemas";
import type { KnowledgeRecord } from "../business/details/knowledge/lib/types";
import { buildBrief, waitingRows } from "./lib/brief";
import { BriefCard } from "./components/BriefCard";
import { WaitingPanel } from "./components/WaitingPanel";

/**
 * E-4 / D21: Home, the tenant app's first tab - the greeting and the brief.
 * Ported from `#greeting` / `#greeting-h1` and `showMorningBrief()` in
 * agencx-prototype-v6.html.
 *
 * The brief carries only kinds backed by real Stage 1 state (see lib/brief.ts).
 * With nothing waiting the screen is the greeting alone: there is deliberately
 * no "you're all caught up" card, because absence is already the message and a
 * card that congratulates the owner for a normal morning is noise.
 *
 * No composer, and that is a scope fact rather than an omission:
 * `POST /api/onboarding/message` 409s once onboarding is confirmed
 * (features/onboarding/controller.py) and no everyday owner-Copilot route
 * replaces it yet. A send box that errors on every send is worse than none.
 */

interface OnboardingState {
  draft: Record<string, string>;
}

/** The prototype greets by time of day; the owner's name comes from O-1. */
function greetingFor(date: Date): string {
  const hour = date.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function HomePage() {
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<OnboardingState>("/api/onboarding/state")
      .then((state) => setName(state.draft?.["owner_display_name"]?.trim() || null))
      .catch(() => setName(null));
  }, []);

  const conversations = useApiQuery<ConversationSummary[]>("/api/conversations");
  const records = useApiQuery<KnowledgeRecord[]>("/api/knowledge/records");

  // Both queries have to have answered before the brief means anything: an
  // empty conversation list is the share nudge's trigger, so composing while
  // one is still in flight would flash a card that is about to be wrong.
  const ready = conversations.data !== undefined && records.data !== undefined;
  const waiting = ready ? waitingRows(conversations.data) : [];
  const items = ready ? buildBrief(conversations.data, records.data) : [];

  return (
    <main className="flex h-full min-h-0 flex-col overflow-y-auto bg-surface px-gutter pb-thread-tail pt-thread-top lg:mx-auto lg:w-full lg:max-w-thread">
      <h1 className="text-greeting font-bold tracking-[var(--text-greeting-tracking)] text-text">
        {greetingFor(new Date())},
        <br />
        {name ?? "there"}.
      </h1>

      <WaitingPanel rows={waiting} />

      <div data-testid="home-brief">
        {items.map((item) => (
          <BriefCard key={item.kind} item={item} />
        ))}
      </div>
    </main>
  );
}
