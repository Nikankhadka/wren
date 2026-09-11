"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { AuthError } from "@supabase/supabase-js";
import { CodeInput } from "@/components/ui/CodeInput";
import { CommandPill } from "@/components/ui/CommandPill";
import {
  AgentLine,
  LedeMessage,
  OwnerBubble,
  Thread,
  ThreadVeil,
  TypingLine,
} from "@/components/ui/Thread";
import { apiFetch, ApiError } from "@/lib/api";
import { getSupabase } from "@/lib/supabase";
import { useAuth } from "@/components/AuthProvider";

/**
 * Arms the send circle when the text CONTAINS something address-shaped, rather
 * than when the whole field is an address. The composer is a chat pill, so
 * "it's sam@shop.com" is a normal answer and must not sit there un-sendable.
 *
 * Also the extraction step below: GoTrue is the only real validator now (a
 * genuinely broken address just gets no mail, exactly like every other OTP
 * flow), so this loose gate plus a bit of trailing-punctuation cleanup is all
 * the client does before handing the address to `signInWithOtp`.
 */
const LOOKS_LIKE_EMAIL = /[^\s@]*@[^\s@]+\.[^\s@]+/;

/** Sentence punctuation clings to the end of an address typed in prose. */
function extractEmail(raw: string): string {
  const candidate = raw.match(LOOKS_LIKE_EMAIL)?.[0] ?? raw.trim();
  return candidate.replace(/[.,;:!?)'"]+$/, "").toLowerCase();
}

/** GoTrue's `error.code` -> the thread's one calm line. Falls back to
 * GoTrue's own message, which is already short and blame-free. */
const OTP_ERROR_COPY: Record<string, string> = {
  validation_failed: "That email does not look quite right. Mind checking it?",
  over_email_send_rate_limit: "That's a lot of codes for one address. Wait a moment and try again.",
  otp_expired: "That code didn't work or expired. Try again, or resend.",
};

function otpErrorMessage(error: AuthError): string {
  if (error.name === "AuthRetryableFetchError") {
    return "Couldn't reach the code service. Check your connection and try again.";
  }
  return (error.code && OTP_ERROR_COPY[error.code]) || error.message;
}

/** Matches the onboarding thread's opening pace (prototype `agentMsg()`). */
const OPENING_PACE_MS = 820;

/**
 * O-2: login-in-chat. The owner authenticates inside the conversation - type an
 * email, receive a 6-digit code, type it back - instead of a sign-up form.
 * GoTrue owns issuance and verification (`signInWithOtp`/`verifyOtp`); a
 * successful verify writes the session cookie `useAuth` reads, and the
 * `/api/tenants` call right after provisions (or fetches) the caller's tenant.
 *
 * This is the first half of the same conversation the onboarding interview
 * continues, so it renders on the same thread primitives as /onboarding: the
 * prototype's full-bleed thread, bare-prose agent turns, berry owner bubbles
 * and pinned composer. The send circle dims rather than disappears until the
 * email parses - design/frontend.md section 6: "the inactive send state is the
 * only validation signal - no red error text".
 */
export default function LoginPage() {
  const router = useRouter();
  const { session, isLoading } = useAuth();

  const [phase, setPhase] = useState<"email" | "code">("email");
  const [draft, setDraft] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [resendAt, setResendAt] = useState<number | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [opened, setOpened] = useState(false);
  const [loginSubmissionInFlight, setLoginSubmissionInFlight] = useState(false);
  const sending = useRef(false);

  useEffect(() => {
    if (!isLoading && session && !loginSubmissionInFlight) {
      router.replace("/onboarding");
    }
  }, [isLoading, loginSubmissionInFlight, session, router]);

  // The opening message is static, so it gets the same typing hold a streamed
  // one would (design/frontend.md section 9).
  useEffect(() => {
    const timer = setTimeout(() => setOpened(true), OPENING_PACE_MS);
    return () => clearTimeout(timer);
  }, []);

  // Deadline-derived rather than a decrementing counter: keying the tick
  // loop on `resendAt` makes each new code request its own lifecycle (no
  // stale timer from a prior request can re-arm resend early), and it stays
  // correct even if the tab was backgrounded and missed ticks.
  useEffect(() => {
    if (resendAt === null) return;
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      const left = Math.max(0, Math.ceil((resendAt - Date.now()) / 1000));
      setSecondsLeft(left);
      // Re-schedules itself only while still counting down, rather than a
      // setInterval that would otherwise keep firing for the rest of the
      // page's life once the cooldown reaches zero.
      if (left > 0) setTimeout(tick, 250);
    };
    tick();
    return () => {
      cancelled = true;
    };
  }, [resendAt]);

  async function submitEmail(value: string, isResend = false) {
    const typed = value.trim();
    if (!typed || sending.current) return;
    sending.current = true;
    const resolved = extractEmail(typed);
    setStatus(null);
    setBusy(true);

    const { error } = await getSupabase().auth.signInWithOtp({ email: resolved });
    if (error) {
      // No red chrome, and the pill keeps what was typed so it can be
      // corrected rather than retyped. A rate-limited resend re-arms the
      // cooldown (GoTrue's own limit didn't reset, so leaving secondsLeft
      // at 0 would show an enabled button that just fails again); any
      // other failure leaves resendAt untouched, exactly as clickable as
      // before.
      if (error.code === "over_email_send_rate_limit") {
        setResendAt(Date.now() + 60_000);
      }
      setStatus(otpErrorMessage(error));
      setBusy(false);
      sending.current = false;
      return;
    }

    setEmail(resolved);
    setDraft("");
    setPhase("code");
    // GoTrue's own per-address resend cadence in production (SMTP_MAX_FREQUENCY).
    setResendAt(Date.now() + 60_000);
    if (isResend) {
      setCode("");
      setStatus("New code sent.");
    }
    setBusy(false);
    sending.current = false;
  }

  async function submitCode(value: string) {
    if (busy) return;
    setCode(value);
    setStatus(null);
    setBusy(true);
    setLoginSubmissionInFlight(true);

    const { error: verifyError } = await getSupabase().auth.verifyOtp({
      email,
      token: value,
      type: "email",
    });
    if (verifyError) {
      setLoginSubmissionInFlight(false);
      setStatus(otpErrorMessage(verifyError));
      setCode("");
      // Re-arm resend immediately: a wrong or expired code shouldn't leave
      // the owner stuck waiting out a cooldown that started with the
      // original send.
      setResendAt(Date.now());
      setBusy(false);
      return;
    }

    try {
      // Empty body: provisions a tenant on the first sign-in, hands back the
      // existing one on every sign-in after (features/tenants/controller.py).
      await apiFetch("/api/tenants", { method: "POST", body: "{}" });
      router.replace("/onboarding");
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : "Something went wrong.";
      await getSupabase().auth.signOut({ scope: "local" });
      setLoginSubmissionInFlight(false);
      setStatus(detail);
      setCode("");
      setPhase("email");
      setDraft(email);
      setBusy(false);
    }
  }

  function handleWrongEmail() {
    setPhase("email");
    setDraft(email);
    setEmail("");
    setCode("");
    setStatus(null);
  }

  if (isLoading || (session && !loginSubmissionInFlight)) return null;

  // Never let the opening message still be "typing" once the conversation has
  // moved past it - a fast answer would otherwise pop the lede in AFTER the
  // reply it precedes.
  const openingShown = opened || phase === "code";

  return (
    <main className="relative isolate flex h-dvh min-h-0 flex-col overflow-hidden bg-surface">
      <ThreadVeil started={phase === "code"} />

      <Thread label="Sign-in conversation" watch={phase} data-testid="login-thread">
        {openingShown ? (
          <LedeMessage question="What's your email?">
            Hi, glad you made it here. I&apos;ll get your business set up and then answer for you,
            so the messages that eat your day stop landing on you.
          </LedeMessage>
        ) : (
          <TypingLine />
        )}

        {phase === "code" ? (
          <>
            <OwnerBubble>{email}</OwnerBubble>
            <AgentLine>Code sent. Pop the six digits in below.</AgentLine>
          </>
        ) : null}
      </Thread>

      <div className="relative z-[1] shrink-0 px-gutter pb-[max(12px,env(safe-area-inset-bottom))] pt-3">
        <div className="mx-auto flex w-full max-w-thread flex-col gap-3">
          {phase === "email" ? (
            <CommandPill
              variant="field"
              value={draft}
              onChange={setDraft}
              onSubmit={submitEmail}
              placeholder="you@example.com"
              busy={busy}
              canSubmit={LOOKS_LIKE_EMAIL.test(draft)}
            />
          ) : (
            <>
              {/* The prototype's `.otp-top`: destination and the escape hatch on
                  one centered row above the cells. */}
              <div className="flex items-center justify-center gap-3 text-meta">
                <span className="text-ink-a40">Code sent to {email}</span>
                <button
                  type="button"
                  onClick={handleWrongEmail}
                  className="flex min-h-11 items-center px-1 text-accent"
                >
                  Wrong email?
                </button>
              </div>
              <CodeInput
                value={code}
                onChange={setCode}
                onComplete={submitCode}
                disabled={busy}
                resetSignal={resendAt}
              />
              {/* `.otp-hint`: a visible countdown while rate-limited (W-12) -
                  the prior disabled-with-no-explanation state made the
                  control look absent. */}
              <button
                type="button"
                onClick={() => void submitEmail(email, true)}
                disabled={secondsLeft > 0 || busy}
                className="mx-auto flex min-h-11 items-center justify-center px-3 text-center text-meta text-accent disabled:pointer-events-none disabled:text-ink-a40"
              >
                {secondsLeft > 0 ? `Resend in ${secondsLeft}s` : "Resend code"}
              </button>
            </>
          )}

          <p role="status" className="min-h-4 text-center text-meta text-text-secondary">
            {status ?? ""}
          </p>
        </div>
      </div>
    </main>
  );
}
