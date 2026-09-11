"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "react-hot-toast";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  AgentLine,
  LedeMessage,
  OwnerBubble,
  ProcessingLine,
  Thread,
  ThreadPill,
  ThreadVeil,
  TypingLine,
} from "@/components/ui/Thread";
import { ThinkingDots } from "@/components/ui/ThinkingDots";
import { useAuth } from "@/components/AuthProvider";
import { apiFetch, apiFetchStream, ApiError } from "@/lib/api";
import {
  type OnboardingKnowledgeBatchResponse,
  type PendingOfferingOutput,
} from "@/lib/api-schemas";
import {
  describeUpload,
  foldReply,
  parseOnboardingEvent,
  type InputSpec,
  type OnboardingDraft,
  type OnboardingState,
} from "@/lib/onboarding";
import { slugShapeError } from "@/lib/slug";
import { BeatComposer } from "./components/BeatComposer";
import {
  type KnowledgeRecord,
  type KnowledgeSection,
  type PendingOffering,
  type ReviewWorkspace,
} from "@/components/knowledge/types";
import { buildWorkspace } from "@/components/knowledge/offerings";
import { ReviewSheet } from "@/components/knowledge/ReviewSheet";
import { useConfirm } from "@/components/ui/ConfirmDialog";

interface Message {
  /** Set only for messages updated after they are pushed (upload stamps). */
  id?: string;
  role: "assistant" | "customer" | "stamp";
  text: string;
  streaming?: boolean;
  /** W-3: a "stamp" message mid-upload - renders animated dots beside it. */
  pending?: boolean;
}

/** A state snapshot without history[] - the SSE ``state`` event carries these. */
interface StateFields {
  stage: string;
  draft: OnboardingDraft;
  completed: boolean;
  input: InputSpec | null;
  can_confirm: boolean;
  suggested_slug: string | null;
  paused_beat: string | null;
  offering_candidates?: PendingOffering[];
}

/**
 * The prototype's `agentMsg()` holds the typing indicator before a message even
 * when that message is static, so pacing reads the same from the first beat
 * (design/frontend.md section 9). Only the opening message of a fresh
 * conversation is paced - restored history renders at once, per the S1 spec's
 * drop-off/return row.
 */
const OPENING_PACE_MS = 820;

/**
 * E-1 US-3: after completion the owner lands on /home. The confirm keeps the
 * "You are live" line readable for this long before the app appears, so go-live
 * reads as one conversation that became an app rather than a hard cut.
 *
 * O-8: this used to be 1400ms spent on an *empty* screen - the thread was
 * replaced by that single line, so the pause read as a stall rather than as a
 * beat. The line is now appended to the conversation the owner has been having,
 * nothing is unmounted, and /home is prefetched the moment confirming becomes
 * possible. With no blank frame to sit through, a shorter hold is enough.
 */
const GO_LIVE_READ_MS = 700;

/** The activation line. Appended to the thread, so it is the assistant's last
 *  word in the conversation rather than a screen of its own. */
const GO_LIVE_LINE =
  "You are live. Your customers get answers now, day or night.";

/**
 * The prototype's `.proc-txt` line while a pasted link is being fetched. The
 * backend leads its URL turn with `progress: reading_site` precisely so this
 * covers the scrape, the ingest and the extraction.
 */
const PROCESSING_COPY: Record<string, string> = {
  reading_site: "Reading your site\u2026",
};

/**
 * W-3: the recovery line every upload failure ends with, whether or not the
 * server gave a reason - it always names the way through, the "+" the file
 * came in from.
 */
const UPLOAD_RECOVERY =
  "Try again with the +, or tell me about it in a sentence.";

/**
 * W-11c: one batch takes five files at most, uploaded three at a time. The
 * thread stamps every file up front and settles them all before the review
 * sheet opens, so these two numbers are the contract that "one review after
 * everything settles" depends on.
 */
const MAX_BATCH_FILES = 5;
const MAX_CONCURRENT_UPLOADS = 3;

function historyToMessages(
  history: { role: string; content: string }[] | undefined,
): Message[] {
  return (history ?? []).map((message) => ({
    role: message.role === "user" ? "customer" : "assistant",
    text: message.content,
  }));
}

/**
 * W-4 US-3: is this confirm failure about the slug specifically? The confirm
 * request's only body field is `slug` (OnboardingConfirmRequest in
 * api.py), so a 422 - pydantic's field_validator on that field - always
 * carries a `/slug` pointer in `errors[]` (api.ts:58 populates it from the
 * ProblemDetails body; errors.py:109-116 builds it from the validator's own
 * ValueError). A 409 never carries `errors[]` (the plain-HTTPException path,
 * main.py:161-166, sends `detail` only) - by the time the confirm button is
 * even visible, the other 409s this endpoint can raise (an unreviewed draft,
 * a paused beat, an already-completed record - controller.py:487-501) are
 * already excluded by this screen's own render condition
 * (`!completed && canConfirm && !workspace`), so the one 409 left that can
 * reach here is the taken-slug conflict (controller.py:535-539).
 */
function isSlugConfirmFailure(err: ApiError): boolean {
  if (err.errors.some((problem) => problem.pointer === "/slug")) return true;
  return err.status === 409;
}

/**
 * The owner-facing text for a slug confirm failure: the specific reason from
 * `errors[]` when pydantic supplied one, the generic `detail` otherwise.
 * Pydantic prefixes a field_validator's raised ValueError with
 * "Value error, " before it reaches `errors[].detail` (errors.py:113 passes
 * the validator's `msg` through verbatim, and pydantic-core adds that prefix
 * ahead of FastAPI) - stripped here so the owner reads slug.py's own message,
 * not its pydantic wrapper.
 */
function confirmFailureDetail(err: ApiError): string {
  const raw = err.errors[0]?.detail ?? err.detail;
  const prefix = "Value error, ";
  return raw.startsWith(prefix) ? raw.slice(prefix.length) : raw;
}

/**
 * W-11c: the batch endpoint answers with the generated PendingOffering-Output
 * shape (every field optional - pydantic omits defaults); the review stack
 * works in the local PendingOffering shape (price_cents and sources
 * guaranteed). Normalize once at the API boundary.
 */
function toPendingOfferings(
  candidates: PendingOfferingOutput[],
): PendingOffering[] {
  return candidates.map((candidate) => ({
    name: candidate.name,
    candidate_id: candidate.candidate_id,
    description: candidate.description,
    price_cents: candidate.price_cents ?? null,
    sources: candidate.sources ?? ["document"],
    source_references: candidate.source_references?.map((reference) => ({
      ...reference,
      supported_fields: reference.supported_fields ?? [],
    })),
    supporting_document_ids: candidate.supporting_document_ids,
    support_state: candidate.support_state ?? "supported",
    price_note: candidate.price_note,
    needs_review: candidate.needs_review,
    possible_matches: candidate.possible_matches,
    price_options: candidate.price_options,
  }));
}

/**
 * The onboarding interview. Ported from the ONBOARDING section of
 * docs/agencx/design/prototypes/agencx-prototype-v6.html: a full-bleed thread
 * that IS the screen - no title, no nav, and no progress surface of any kind
 * (design/frontend.md section 9: "the thread is the progress indicator"). The
 * composer renders whatever widget the server's InputSpec asks for
 * (BeatComposer); confirm is server-gated via ``can_confirm`` rather than a
 * client-side draft-length guess.
 *
 * The captured profile is shown back on the Business tab (S2), not here.
 */
export default function OnboardingPage() {
  const router = useRouter();
  // O-6: the address O-2 captured at login, offered as a one-tap chip on the
  // contact beat. Only the client holds it - it lives in Supabase auth, not in
  // the `users` table the API can read.
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [opening, setOpening] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [stage, setStage] = useState("");
  const [input, setInput] = useState<InputSpec | null>(null);
  const [canConfirm, setCanConfirm] = useState(false);
  const [pausedBeat, setPausedBeat] = useState<string | null>(null);
  // W-4: the address is derived, never latched. `suggestedSlug` is set
  // unconditionally on every state read - the server recomputes it from the
  // draft's business name every time (controller.py:175-181, 121-125), so it
  // is always current. `slugDraft` stays null until the owner types into the
  // field, then holds exactly what they typed. `publicSlug` below is the
  // derived value: the owner's text once they have any, the live suggestion
  // until then. This is what makes every path that reaches the confirm step
  // (initial load, ordinary answers, optional-knowledge skip, review save,
  // review discard, reload - W-4 US-1) supply the suggestion automatically,
  // and what makes a business-name correction keep following it only until
  // the owner edits the field (W-4 US-2): there is no separate
  // `applySlugSuggestion()` call to add to six call sites, so do not
  // reintroduce the old `current || fields.suggested_slug` latch here - that
  // shape is exactly what let saveKnowledge/discardKnowledge bypass the
  // prefill in the first place.
  const [suggestedSlug, setSuggestedSlug] = useState("");
  const [slugDraft, setSlugDraft] = useState<string | null>(null);
  const publicSlug = slugDraft ?? suggestedSlug;
  // W-4 US-3: the slug-specific confirm failure, shown on the Input's own
  // `error` prop rather than the shared status line below.
  const [slugError, setSlugError] = useState<string | null>(null);
  // W-7: the go-live screen confirms only the address. The business name is
  // read back for reassurance (not editable - it was captured during the
  // interview), so the page holds the value but no input state for it.
  const [businessName, setBusinessName] = useState("");
  const [busy, setBusy] = useState(false);
  const [processing, setProcessing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [ownerOfferings, setOwnerOfferings] = useState<PendingOffering[]>([]);
  const [drafts, setDrafts] = useState<KnowledgeRecord[]>([]);
  const [workspace, setWorkspace] = useState<ReviewWorkspace | null>(null);
  const [open, setOpen] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  // Removing a review source asks first - the dialog renders beside the
  // sheet below, above it, never inside it.
  const { confirm: confirmRemove, dialog: confirmDialog } = useConfirm();
  const [openingPaced, setOpeningPaced] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const goLiveTimer = useRef<number | null>(null);

  function applyStateFields(fields: StateFields) {
    setCompleted(fields.completed);
    setStage(fields.stage);
    setInput(fields.input);
    setCanConfirm(fields.can_confirm);
    setPausedBeat(fields.paused_beat);
    setOwnerOfferings(fields.offering_candidates ?? []);
    setBusinessName((current) => current || fields.draft.business_name || "");
    // W-4 US-1/US-2: unconditional, every time - see the `suggestedSlug`
    // declaration above for why this alone is enough for every confirm-
    // opening path, and why it never overwrites an owner-entered address.
    setSuggestedSlug(fields.suggested_slug ?? "");
  }

  useEffect(() => {
    Promise.all([
      apiFetch<OnboardingState>("/api/onboarding/state"),
      apiFetch<KnowledgeRecord[]>("/api/knowledge/records"),
    ])
      .then(([state, records]) => {
        // E-1: a business that is already live has no interview left to run -
        // it belongs in the app. The in-session confirm still finishes here,
        // so the owner reads "you are live" before the next visit redirects.
        if (state.completed) {
          router.replace("/home");
          return;
        }
        applyStateFields(state);
        const pending = records.filter((record) => record.status === "draft");
        setDrafts(pending);
        if (pending[0]) {
          setCanConfirm(false);
          // W-11c: the combined review opens over every pending draft, not the
          // first one - the sheet's Sources panel reviews them together.
          setWorkspace(buildWorkspace(pending, state.offering_candidates ?? [], pending[0].id));
          setOpen(true);
        }
        const restored = historyToMessages(state.history);
        if (restored.length > 0) {
          // A returning owner sees the whole thread at once - never re-paced.
          setMessages(restored);
          setOpeningPaced(true);
        } else if (!state.completed) {
          setOpening(state.prompt);
        }
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.detail : "Failed to load onboarding",
        ),
      )
      .finally(() => setLoaded(true));
  }, [router]);

  /**
   * O-8: warm /home the moment the interview is finishable. The route pulls its
   * own brief from three endpoints on mount, so an unprefetched navigation puts
   * that cold work between the confirm and the first painted frame - which is
   * the part that read as a lag.
   */
  useEffect(() => {
    if (canConfirm) router.prefetch("/home");
  }, [canConfirm, router]);

  // Never leave a navigation queued against an unmounted page.
  useEffect(
    () => () => {
      if (goLiveTimer.current !== null)
        window.clearTimeout(goLiveTimer.current);
    },
    [],
  );

  // Hold the typing indicator ahead of the (static) opening message.
  useEffect(() => {
    if (!opening || openingPaced) return;
    const timer = setTimeout(() => setOpeningPaced(true), OPENING_PACE_MS);
    return () => clearTimeout(timer);
  }, [opening, openingPaced]);

  function updateById(id: string, update: Partial<Message>) {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === id ? { ...message, ...update } : message,
      ),
    );
  }

  function updateLastAssistant(update: (last: Message) => Partial<Message>) {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last && last.role === "assistant")
        next[next.length - 1] = { ...last, ...update(last) };
      return next;
    });
  }

  async function sendText(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setError(null);
    setBusy(true);
    setProcessing(null);
    setMessages((prev) => [
      ...prev,
      { role: "customer", text: trimmed },
      { role: "assistant", text: "", streaming: true },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await apiFetchStream("/api/onboarding/message/stream", {
        method: "POST",
        body: JSON.stringify({ text: trimmed }),
        signal: controller.signal,
      });
      if (!res.body) throw new Error("onboarding request failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let reply = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const raw of events) {
          if (!raw.startsWith("data: ")) continue;
          const event = parseOnboardingEvent(raw.slice("data: ".length));
          if (!event) continue;

          switch (event.type) {
            case "progress":
              // Named work replaces the dots; anything unnamed leaves them up.
              setProcessing(PROCESSING_COPY[event.stage] ?? null);
              break;
            case "token":
            case "redraft":
            case "reply":
              setProcessing(null);
              reply = foldReply(reply, event);
              updateLastAssistant(() => ({ text: reply }));
              break;
            case "state":
              applyStateFields(event);
              break;
            case "done":
              updateLastAssistant(() => ({ streaming: false }));
              break;
            case "error":
              updateLastAssistant(() => ({ streaming: false }));
              setError(event.detail ?? "Something went wrong");
              break;
          }
        }
      }
      const records = await apiFetch<KnowledgeRecord[]>("/api/knowledge/records");
      const pending = records.filter((record) => record.status === "draft");
      setDrafts(pending);
      if (pending[0]) {
        setCanConfirm(false);
        // W-11b/W-11c: keep the workspace id across rebuilds so the sheet
        // never remounts mid-session, and review every pending draft together.
        setWorkspace(buildWorkspace(pending, ownerOfferings, workspace?.id ?? pending[0].id));
        setOpen(true);
      }
    } catch (err) {
      // W-3: an aborted stream and a failed request both leave no reply behind
      // - either way, drop the empty placeholder bubble (or mark it settled if
      // some text already arrived) rather than leaving it "streaming" forever.
      // A failed request used to skip this, so its TypingLine stuck around
      // after busy cleared - two pending indicators disagreeing about whether
      // the turn was still in flight.
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === "assistant" && last.text === "")
          return prev.slice(0, -1);
        const next = [...prev];
        if (last) next[next.length - 1] = { ...last, streaming: false };
        return next;
      });
      if (!(err instanceof Error && err.name === "AbortError")) {
        setError(err instanceof ApiError ? err.detail : "Something went wrong");
      }
    } finally {
      abortRef.current = null;
      setProcessing(null);
      setBusy(false);
    }
  }

  async function sendSelection(values: string[], label: string) {
    if (busy) return;
    setError(null);
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      { role: "customer", text: label },
      { role: "assistant", text: "", streaming: true },
    ]);
    try {
      const state = await apiFetch<OnboardingState>("/api/onboarding/message", {
        method: "POST",
        body: JSON.stringify({ selection: { beat: stage, values } }),
      });
      applyStateFields(state);
      setMessages(historyToMessages(state.history));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        try {
          const state = await apiFetch<OnboardingState>("/api/onboarding/state");
          applyStateFields(state);
          setMessages(historyToMessages(state.history));
          setError("Setup refreshed. Choose your answer again.");
        } catch {
          setError("Setup changed. Refresh the page and try again.");
        }
      } else {
        setMessages((prev) => prev.slice(0, -2));
        setError(err instanceof ApiError ? err.detail : "Something went wrong");
      }
    } finally {
      setBusy(false);
    }
  }

  async function resumePausedBeat() {
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const state = await apiFetch<OnboardingState>("/api/onboarding/message", {
        method: "POST",
        body: JSON.stringify({ resume: true }),
      });
      applyStateFields(state);
      setMessages(historyToMessages(state.history));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  /**
   * W-11c: run at most `limit` tasks concurrently, resolving in input order -
   * results are indexed by task position, so the caller can match each outcome
   * to its task regardless of settle order.
   */
  async function runBounded<T>(
    tasks: (() => Promise<T>)[],
    limit: number,
  ): Promise<PromiseSettledResult<T>[]> {
    const results: PromiseSettledResult<T>[] = [];
    let cursor = 0;
    async function worker() {
      while (cursor < tasks.length) {
        const index = cursor;
        cursor += 1;
        try {
          results[index] = { status: "fulfilled", value: await tasks[index]() };
        } catch (reason) {
          results[index] = { status: "rejected", reason };
        }
      }
    }
    await Promise.all(
      Array.from({ length: Math.min(limit, tasks.length) }, () => worker()),
    );
    return results;
  }

  /**
   * W-11c: the shared upload core behind the composer's "+" and the review
   * sheet's Add source and Replace paths. A batch caps at five files, uploaded
   * three at a time; every file gets its own stamp up front and settles to
   * "· ready" or "· failed". Returns the accepted draft records in input order.
   * A stored failure (a 201 with status "failed") is never returned - the file
   * is kept in Knowledge for retry, and never joins drafts or the workspace.
   * Callers own the busy state and the follow-up drafts/workspace surgery.
   */
  async function uploadDrafts(files: File[]): Promise<KnowledgeRecord[]> {
    // W-11c: a batch caps at five files - the first five are processed, the
    // rest are turned away in one line.
    const batch = files.slice(0, MAX_BATCH_FILES);
    if (files.length > MAX_BATCH_FILES) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "I can take up to 5 files at once..." },
      ]);
    }
    // describeUpload rejections (an image, an unknown extension) answer at
    // once with no stamp; accepted files get their pending stamp up front,
    // in input order, before any upload starts.
    const queue: { file: File; stampId: string }[] = [];
    for (const file of batch) {
      const verdict = describeUpload(file.name);
      if (!verdict.accepted) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: verdict.message },
        ]);
        continue;
      }
      const stampId = crypto.randomUUID();
      queue.push({ file, stampId });
      // W-3: the stamp itself carries the animated processing state
      // (ThinkingDots, rendered beside `message.text` in the thread) instead
      // of a frozen "adding\u2026" suffix - reading and scrolling stay available
      // while extraction runs, and `pending` is always resolved explicitly
      // below, on both the success and the failure path.
      setMessages((prev) => [
        ...prev,
        { id: stampId, role: "stamp", text: file.name, pending: true },
      ]);
    }
    const accepted: KnowledgeRecord[] = [];
    const results = await runBounded(
      queue.map((entry) => () => uploadOne(entry)),
      MAX_CONCURRENT_UPLOADS,
    );
    for (let index = 0; index < results.length; index += 1) {
      const result = results[index];
      const { file, stampId } = queue[index];
      if (result.status === "fulfilled" && result.value) {
        accepted.push(result.value);
      } else if (result.status === "rejected") {
        const err = result.reason;
        updateById(stampId, {
          text: `${file.name} \u00b7 failed`,
          pending: false,
        });
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text:
              err instanceof ApiError && err.detail
                ? `I couldn't read that one. ${err.detail} ${UPLOAD_RECOVERY}`
                : `I couldn't read that one. ${UPLOAD_RECOVERY}`,
          },
        ]);
      }
    }
    return accepted;

    async function uploadOne(entry: {
      file: File;
      stampId: string;
    }): Promise<KnowledgeRecord | null> {
      const form = new FormData();
      form.append("file", entry.file);
      form.append("doc_type", "other");
      const draft = await apiFetch<KnowledgeRecord>(
        "/api/knowledge/drafts/upload",
        {
          method: "POST",
          body: form,
        },
      );
      if (draft.status === "failed") {
        // W-11a: a 201 that parks a failed draft - the file is kept so the
        // owner can retry it from Knowledge. It is not a reviewable draft, so
        // it never joins drafts or the workspace.
        updateById(entry.stampId, {
          text: `${entry.file.name} \u00b7 failed`,
          pending: false,
        });
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text: "It's kept in Knowledge so you can retry it.",
          },
        ]);
        return null;
      }
      updateById(entry.stampId, {
        text: `${entry.file.name} \u00b7 ready`,
        pending: false,
      });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `I found ${entry.file.name}. Review it before it answers customers.`,
        },
      ]);
      return draft;
    }
  }

  /**
   * Files attached through the pill's "+". Knowledge is never a blocking beat:
   * a refused or failed file leaves one calm line and the interview carries
   * on. The review sheet opens only once every file has settled - never on the
   * first accepted draft.
   *
   * ponytail: the stamps are client-side only - the ingested document is
   * persisted, its stamp is not, so a reload shows the thread without them.
   * Persisting them needs an onboarding-side record of the attachment.
   */
  async function uploadFiles(files: File[]) {
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const accepted = await uploadDrafts(files);
      if (accepted.length > 0) {
        setCanConfirm(false);
        // W-11c: one rebuild after everything settles - never per draft. The
        // workspace id carries over so the sheet does not remount mid-flight.
        setDrafts((previous) => [...previous, ...accepted]);
        setWorkspace(
          buildWorkspace(
            [...(workspace?.documents ?? []), ...accepted],
            ownerOfferings,
            workspace?.id,
          ),
        );
        setOpen(true);
      }
    } finally {
      setBusy(false);
    }
  }

  /**
   * W-11c: Add source from inside the review sheet. Same upload core as the
   * composer, then the workspace grows by the accepted records (id stable -
   * W-11b) and the sheet merges their candidates into its own list.
   */
  async function addSources(files: File[]): Promise<KnowledgeRecord[]> {
    if (busy) return [];
    setError(null);
    setReviewError(null);
    setBusy(true);
    try {
      const accepted = await uploadDrafts(files);
      if (accepted.length > 0) {
        setCanConfirm(false);
        setDrafts((previous) => [...previous, ...accepted]);
        setWorkspace(
          buildWorkspace(
            [...(workspace?.documents ?? []), ...accepted],
            ownerOfferings,
            workspace?.id,
          ),
        );
      }
      return accepted;
    } finally {
      setBusy(false);
    }
  }

  /**
   * W-11c: replace one source from the review sheet. Upload first, then delete
   * the old record only once the new one is a reviewable draft - an upload
   * failure returns null with the old document untouched and the DELETE never
   * fired. A delete failure after a successful upload surfaces the error and
   * refreshes the record list (the orphaned new draft is then visible and
   * recoverable); the old document is still there.
   */
  async function replaceSource(
    documentId: string,
    file: File,
  ): Promise<KnowledgeRecord | null> {
    if (busy) return null;
    setError(null);
    setReviewError(null);
    setBusy(true);
    try {
      const accepted = await uploadDrafts([file]);
      const uploaded = accepted[0];
      if (!uploaded) return null;
      try {
        await apiFetch(`/api/knowledge/records/${documentId}`, {
          method: "DELETE",
        });
      } catch (err) {
        setReviewError(
          err instanceof ApiError
            ? err.detail
            : "I couldn't replace that source. Your old one is still there - try again.",
        );
        const records = await apiFetch<KnowledgeRecord[]>(
          "/api/knowledge/records",
        ).catch(() => null);
        if (records) setDrafts(records.filter((record) => record.status === "draft"));
        return null;
      }
      const records = await apiFetch<KnowledgeRecord[]>("/api/knowledge/records");
      const next = records.find((record) => record.id === uploaded.id) ?? uploaded;
      setDrafts(records.filter((record) => record.status === "draft"));
      // Old position replaced with the new record; workspace id stays put.
      setWorkspace((previous) =>
        previous
          ? {
              ...previous,
              documents: previous.documents.map((doc) =>
                doc.id === documentId ? next : doc,
              ),
            }
          : previous,
      );
      return next;
    } catch (err) {
      setReviewError(
        err instanceof ApiError ? err.detail : "I couldn't replace that source.",
      );
      return null;
    } finally {
      setBusy(false);
    }
  }

  /**
   * W-11c: remove one source from the review sheet. Deletes the record, then
   * refreshes the list. Removing the last document clears the workspace and
   * unblocks confirm.
   */
  async function removeSource(documentId: string): Promise<void> {
    if (!workspace || busy) return;
    setError(null);
    setReviewError(null);
    setBusy(true);
    try {
      await apiFetch(`/api/knowledge/records/${documentId}`, {
        method: "DELETE",
      });
      const records = await apiFetch<KnowledgeRecord[]>("/api/knowledge/records");
      const remaining = workspace.documents.filter((doc) => doc.id !== documentId);
      setDrafts(records.filter((record) => record.status === "draft"));
      if (remaining.length === 0) {
        setWorkspace(null);
        setOpen(false);
        setCanConfirm(true);
      } else {
        setWorkspace({ ...workspace, documents: remaining });
      }
    } catch (err) {
      setReviewError(
        err instanceof ApiError ? err.detail : "I couldn't remove that source.",
      );
    } finally {
      setBusy(false);
    }
  }

  /**
   * W-11c: the review save publishes every workspace document in one batch
   * call. The endpoint always answers 200 - a document's own failure (price
   * conflict, or a hard failure at publish time) lands in `failed`, never as a
   * network error, and never aborts the documents that did publish.
   *
   * On any failure the workspace is rebuilt over the remaining documents
   * (refetch /api/knowledge/records, keep the workspace id so the sheet stays
   * mounted, keep the previous document order) with a per-document `errors`
   * map and a summary line; the sheet shows the per-doc messages under each
   * source. On full success the workspace dies, the confirm step unblocks, and
   * the resolved candidates are returned for the sheet to adopt.
   */
  async function saveKnowledge(
    documents: { document_id: string; sections: KnowledgeSection[] }[],
    offerings: PendingOffering[],
    acceptPriceChanges = false,
  ): Promise<PendingOffering[] | null> {
    if (!workspace) return null;
    setReviewError(null);
    setBusy(true);
    try {
      const response = await apiFetch<OnboardingKnowledgeBatchResponse>(
        "/api/onboarding/knowledge/batch",
        {
          method: "PUT",
          body: JSON.stringify({
            documents,
            offerings,
            accept_price_changes: acceptPriceChanges,
          }),
        },
      );
      const candidates = toPendingOfferings(response.offering_candidates);
      const failedIds = new Set(
        response.failed.map((failure) => failure.document_id),
      );
      if (failedIds.size > 0) {
        const records = await apiFetch<KnowledgeRecord[]>("/api/knowledge/records");
        // Keep the previous document order; a failure whose document is
        // already gone (a "document not found" ghost) simply drops out.
        const remaining: KnowledgeRecord[] = [];
        for (const doc of workspace.documents) {
          const record = records.find((candidate) => candidate.id === doc.id);
          if (record && failedIds.has(record.id)) remaining.push(record);
        }
        setOwnerOfferings(candidates);
        setDrafts(records.filter((record) => record.status === "draft"));
        if (remaining.length === 0) {
          // Every failure was a ghost (document already gone) - treat the
          // batch as done rather than leaving an empty sheet behind.
          setWorkspace(null);
          setOpen(false);
          setCanConfirm(true);
          return candidates;
        }
        const errors: Record<string, string> = {};
        for (const failure of response.failed) {
          errors[failure.document_id] = failure.error;
        }
        setWorkspace({
          ...buildWorkspace(remaining, candidates, workspace.id),
          errors,
        });
        setOpen(true);
        setCanConfirm(false);
        setReviewError(
          "Some documents couldn't be saved. See the message under each source, then save again.",
        );
        return candidates;
      }
      setOwnerOfferings(candidates);
      setDrafts([]);
      setWorkspace(null);
      setOpen(false);
      setCanConfirm(true);
      return candidates;
    } catch (err) {
      // A network-level failure - the batch never ran, nothing published.
      setReviewError(
        err instanceof ApiError
          ? err.detail
          : "I couldn't save that information.",
      );
      return null;
    } finally {
      setBusy(false);
    }
  }

  /**
   * W-11c: discard deletes every document still in the review, not just the
   * first - per-source Remove covers individuals. All published-side drafts go
   * with the workspace, and confirm unblocks.
   */
  async function discardKnowledge() {
    if (!workspace) return;
    setReviewError(null);
    setBusy(true);
    try {
      await Promise.all(
        workspace.documents.map((doc) =>
          apiFetch(`/api/knowledge/records/${doc.id}`, { method: "DELETE" }),
        ),
      );
      const discarded = new Set(workspace.documents.map((doc) => doc.id));
      setDrafts((previous) =>
        previous.filter((draft) => !discarded.has(draft.id)),
      );
      setWorkspace(null);
      setOpen(false);
      setCanConfirm(true);
    } catch (err) {
      setReviewError(
        err instanceof ApiError
          ? err.detail
          : "I couldn't discard those drafts.",
      );
    } finally {
      setBusy(false);
    }
  }

  function handleStop() {
    abortRef.current?.abort();
  }

  async function handleConfirm() {
    setError(null);
    setSlugError(null);
    // W-4 US-3: client-side shape/length check first, mirroring slug.py -
    // catches an invalid address before any network call, with no `busy`
    // flip at all (the button stays clickable for another try).
    const shapeError = slugShapeError(publicSlug);
    if (shapeError) {
      setSlugError(shapeError);
      toast.error(shapeError);
      return;
    }
    setBusy(true);
    try {
      await apiFetch("/api/onboarding/confirm", {
        method: "POST",
        body: JSON.stringify({ slug: publicSlug }),
      });
      setCompleted(true);
      setCanConfirm(false);
      setInput(null);
      // The payoff line joins the conversation instead of replacing it.
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: GO_LIVE_LINE },
      ]);
      goLiveTimer.current = window.setTimeout(
        () => router.replace("/home"),
        GO_LIVE_READ_MS,
      );
      // Deliberately no setBusy(false): the button stays held until the route
      // changes. Releasing it re-armed a second click, and the second confirm
      // 409s "already confirmed" - painting an error over the live line.
    } catch (err) {
      // W-4 US-3: a slug problem (invalid/reserved 422, taken-slug 409) goes
      // on the field, with a toast for visibility; anything else (the
      // network failure this catch also handles, since apiFetch throws a
      // plain Error for that - not ApiError) keeps using the shared status
      // line below the composer. The draft and the entered address are both
      // untouched either way - only `error`/`slugError` and `busy` change.
      if (err instanceof ApiError && isSlugConfirmFailure(err)) {
        const message = confirmFailureDetail(err);
        setSlugError(message);
        toast.error(message);
      } else {
        setError(
          err instanceof ApiError
            ? err.detail
            : "Something went wrong. Please try again.",
        );
      }
      setBusy(false);
    }
  }

  // The veil lifts for good once the owner has answered once (prototype
  // `#phone.started`).
  const started = messages.some((message) => message.role === "customer");
  // Never let the opening message still be "typing" once the conversation has
  // moved past it - a fast answer would otherwise pop the lede in AFTER the
  // reply it precedes.
  const openingShown = openingPaced || messages.length > 0;

  if (!loaded) {
    return (
      <main className="flex flex-1 items-center justify-center bg-surface p-8">
        <div
          aria-busy="true"
          className="h-8 w-8 animate-pulse rounded-full bg-surface-container"
        />
      </main>
    );
  }

  return (
    <main className="relative isolate flex h-dvh min-h-0 flex-col overflow-hidden bg-surface">
      <ThreadVeil started={started} />

      <Thread
        label="Onboarding conversation"
        watch={messages}
        data-testid="onboarding-thread"
      >
        {opening ? (
          openingShown ? (
            <LedeMessage>{opening}</LedeMessage>
          ) : (
            <TypingLine />
          )
        ) : null}
        {messages.map((message, index) =>
          message.role === "customer" ? (
            <OwnerBubble key={index}>{message.text}</OwnerBubble>
          ) : message.role === "stamp" ? (
            <ThreadPill key={index}>
              {message.text}
              {/* W-3: the animated processing state for this stamp - aria-hidden
                  and no live region of its own, so it does not collide with the
                  thread's own role="log" (Thread.tsx:55-57). */}
              {message.pending ? <ThinkingDots className="ml-2" /> : null}
            </ThreadPill>
          ) : message.streaming && !message.text ? (
            processing ? (
              <ProcessingLine key={index}>{processing}</ProcessingLine>
            ) : (
              <TypingLine key={index} />
            )
          ) : (
            <AgentLine key={index} streaming={message.streaming ?? false}>
              {message.text}
            </AgentLine>
          ),
        )}
      </Thread>

      <div className="relative z-[1] shrink-0 px-gutter pb-[max(12px,env(safe-area-inset-bottom))] pt-3">
        <div className="mx-auto w-full max-w-thread">
          {/* W-11c: the persistent "Documents ready to review" card from
              15-document-review.md - a closed-but-unfinished draft always has
              a way back. Replaces the W-11b bare button; the button keeps the
              W-11b testid so onboarding-url.spec.ts still finds it. Styled
              after the home screen's BriefCard (same surface). */}
          {!open && drafts.length > 0 ? (
            <div
              data-testid="onboarding-ready-card"
              className="mt-4 animate-rise rounded-card border border-hairline bg-surface px-[18px] py-4 shadow-card"
            >
              <p className="text-card-hl font-medium text-text">Documents ready to review</p>
              <p className="mt-1 text-meta text-ink-a40">
                {drafts.length === 1
                  ? "1 source is read and waiting"
                  : `${drafts.length} sources are read and waiting`}
              </p>
              <Button
                variant="secondary"
                onClick={() => setOpen(true)}
                className="mt-3 w-full sm:w-auto"
                data-testid="onboarding-reopen-review"
              >
                Review documents
              </Button>
            </div>
          ) : null}
          {!completed && canConfirm && !workspace ? (
            <div className="flex flex-col gap-3">
              {businessName ? (
                <p className="text-meta text-ink-a40" data-testid="onboarding-going-live-as">
                  Going live as {businessName}.
                </p>
              ) : null}
              <Input
                label="Your business page"
                value={publicSlug}
                onChange={(event) => {
                  setSlugDraft(event.target.value.toLowerCase());
                  setSlugError(null);
                }}
                help={`Shared as agencx.app/${publicSlug}`}
                error={slugError ?? undefined}
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                disabled={busy}
                data-testid="onboarding-public-slug"
              />
              <Button
                onClick={handleConfirm}
                loading={busy}
                data-testid="onboarding-confirm"
              >
                Confirm and go live
              </Button>
            </div>
          ) : !completed && pausedBeat ? (
            <div className="flex flex-col gap-2" data-testid="onboarding-paused">
              <p className="text-meta text-ink-a40">
                Finish this field when you are ready to keep setting up your assistant.
              </p>
              <Button onClick={() => void resumePausedBeat()} loading={busy}>
                Try again
              </Button>
            </div>
          ) : !completed && input ? (
            <BeatComposer
              key={stage}
              input={input}
              busy={busy}
              onText={(text) => void sendText(text)}
              onSelection={(values, label) => void sendSelection(values, label)}
              onStop={handleStop}
              ownerEmail={user?.email ?? null}
              onFiles={stage === "knowledge" ? (files) => void uploadFiles(files) : undefined}
            />
          ) : null}

          {/* Mounted unconditionally (only the text toggles) - screen readers
              reliably announce changes inside an existing live region, but
              often miss one that appears and disappears. Sits outside the
              thread's role="log" so the two never compete. */}
          {/* W-3: TypingLine in the thread is the sole pending-turn indicator
              now - this slot holds nothing while a turn is in flight, and
              carries only the error text. */}
          <p
            role="status"
            data-testid={error ? "onboarding-error" : undefined}
            className={`mt-2 h-4 text-meta ${error ? "text-danger" : "text-text-secondary"}`}
          >
            {error ?? ""}
          </p>
          {/* Onboarding half of the privacy disclosure (15-document-review.md,
              "Privacy disclosure") - unconditional, shortened per founder
              request to one sentence, no vendor name. The fuller disclosure
              stays on Business > Knowledge, which has room for it. */}
          <p
            data-testid="onboarding-privacy-disclosure"
            className="mt-2 text-meta text-ink-a40"
          >
            {"Your documents stay private to your business, and nothing answers customers until you review and save it."}
          </p>
        </div>
      </div>
      <ReviewSheet
        workspace={workspace}
        open={open}
        busy={busy}
        priceConflict={reviewError}
        onboarding
        onClose={() => {
          setReviewError(null);
          setOpen(false);
        }}
        onSave={(documents, offerings, acceptPriceChanges) =>
          saveKnowledge(documents, offerings, acceptPriceChanges)
        }
        onDiscard={() => void discardKnowledge()}
        onAddSource={(files) => addSources(files)}
        onReplaceSource={(documentId, file) => replaceSource(documentId, file)}
        onRemoveSource={(documentId) => removeSource(documentId)}
        confirmRemove={confirmRemove}
      />
      {confirmDialog}
    </main>
  );
}
