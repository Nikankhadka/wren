# Phase 16: authentication OTP reliability

This phase closes two authentication reliability gaps found in the real login
surface. The product contract remains D23: email verification codes are six
digits. W-13 corrects configuration drift first, then W-12 makes recovery from
a mistyped or missed code obvious and usable. The tickets are independently
shippable and must land in that order before W-11c implementation resumes.

The resend control already exists in the shared login and signup flow. It is
currently disabled during the sixty-second cooldown without showing the
remaining time, which makes it appear absent and leaves a failed attempt
without a useful recovery action.

## Evidence and decisions

1. `frontend/src/app/(tenant-admin)/login/page.tsx` uses the same email OTP
   flow reached from signup. It renders `Didn't get it? Resend`, but only
   exposes a disabled boolean while `resendReady` is false. It does not show a
   countdown, and a failed verification does not re-arm that control.
2. `frontend/src/components/ui/CodeInput.tsx` hardcodes six cells, truncates
   pasted input to six characters, and submits when all six cells are filled.
   The deployed-surface probe with an eight-digit mocked email submitted only
   `123456`, proving that a hosted length mismatch cannot be repaired in the
   client by accepting a longer code.
3. Local GoTrue pins `GOTRUE_MAILER_OTP_EXP=600` in `docker-compose.yml`, but
   does not explicitly pin the OTP length. Hosted Supabase's
   `mailer_otp_length` has not yet been inspected because no Management API
   token is available in this workspace. Do not claim that it is six or change
   it until the GET check is made.
4. The existing six-digit contract and the existing Mailpit-backed login E2E
   coverage are the compatibility baseline. No dynamic client code length is
   introduced by these tickets.

## W-13: OTP length parity

Branch `fix/w-13-otp-length-parity`. This is the operational/configuration
ticket and lands before W-12.

### User stories

- As a user, a code sent by development, staging, or production has the same
  six-digit shape that the login screen accepts.
- As an operator, I can prove the hosted Auth configuration before changing
  it, and can verify a newly issued code through the real login surface after
  the change.

### Technical scope

- Preserve D23's six-digit contract. Add an explicit local GoTrue
  `GOTRUE_MAILER_OTP_LENGTH: "6"` setting beside the existing OTP expiry.
- Update `docs/agencx/deploy.md`'s Auth Management API GET/PATCH examples to
  include `mailer_otp_length` and state that the GET must precede any PATCH.
- With a valid project Management API token, GET the hosted Auth service
  configuration, record the observed value in the ticket/PR evidence, and
  PATCH `mailer_otp_length` to `6` only when the observed value differs.
- After any hosted change, request a fresh email OTP and complete login with
  the complete six-digit value through the deployed UI. A code issued before
  the change is not valid evidence. Verify both staging and production when
  they point at different Auth projects.
- Keep `CodeInput` six cells and its existing generated/API contract. Do not
  add a dynamic length setting or infer length from an email.

### Non-goals

- Changing the six-digit product decision, expiry duration, resend rate limit,
  email templates, SMTP provider, or signup policy.
- Making a client accept eight- or ten-digit codes to mask configuration drift.
- Claiming hosted parity until the authenticated GET, fresh email, and real
  login checks are complete.

### Definition of done

- [x] Local GoTrue explicitly generates six-digit OTPs and local Mailpit login
      coverage passes. `GOTRUE_MAILER_OTP_LENGTH: "6"` is pinned beside the
      existing expiry in `docker-compose.yml`; confirmed live in the running
      container and all nine `frontend/e2e/auth-login.spec.ts` cases pass.
- [ ] Hosted Auth `mailer_otp_length` was inspected before a PATCH; the
      observed value and whether a PATCH was needed are recorded as evidence.
      **Open - no Management API token available in this environment.**
- [ ] A fresh hosted email contains six digits and that code completes login
      through the deployed UI. **Open, blocked on the item above.**
- [x] No dynamic client length or unrelated Auth behavior was introduced.
      `CodeInput.tsx` and `login/page.tsx` are untouched.
- [x] Relevant config/docs checks and the existing auth E2E coverage are
      green: `make check` (lint, typecheck, 1007 backend + 120 frontend
      tests) and `frontend/e2e/auth-login.spec.ts`,
      `auth-credentials-validation.spec.ts`, `auth-platform.spec.ts` (19
      cases) all pass.

### Operational check

Use the project Management API credentials from the operator environment, not
from source control. GET the Auth service config, compare
`.mailer_otp_length` with `6`, PATCH only on mismatch, then request a new code
and verify it end to end. If credentials are unavailable, the code/config
portion may be reviewed, but the hosted acceptance item remains open.

**Status: local config/docs portion shipped. Hosted GET/PATCH/verify step
still needs an operator with a [Supabase personal access
token](https://supabase.com/dashboard/account/tokens) - the Supabase MCP
connector in this workspace is unauthenticated and has no Auth-config tool
regardless.**

## W-12: OTP resend and retry recovery

Branch `fix/w-12-otp-resend-recovery`, based on development after W-13.

### User stories

- As a user who did not receive a code, I can see when resend becomes
  available and request another code without guessing why the control is
  disabled.
- As a user who entered a wrong or expired code, I can immediately start again
  in the first digit and either resend when allowed or see an actionable
  inline error.
- As a user, clicking resend once sends one request, visibly confirms the
  result, and starts a new cooldown without duplicate requests.

### Technical scope

- Keep the existing login/signup flow and Button/Thread visual language. While
  rate limited, show `Resend in Ns` and explain the disabled state accessibly;
  after sixty seconds show an enabled `Resend code`. Preserve a minimum
  forty-four pixel touch target and the existing focus-visible treatment.
- Use one countdown lifecycle per code request. Reset it after a successful
  resend, guard the loading state against duplicate requests, and surface a
  recoverable inline network/Auth error without losing the email or trapping
  the user.
- After a failed verification, clear stale code cells and focus Digit 1. A
  successful resend also clears stale digits and focuses Digit 1. Do not
  submit a partial or stale code automatically.
- Keep the six-digit `CodeInput` contract from W-13 and preserve the existing
  sign-in, signup redirect, wrong-code, expired-code, and Mailpit behavior.
- Add deterministic route-mocked Playwright coverage at the mobile and
  desktop viewports for the initial countdown, failed-code clear/refocus,
  cooldown expiry, one resend request, cooldown reset, success feedback, and
  recoverable failure. Retain the existing real GoTrue/Mailpit coverage.

### Non-goals

- Changing server-side OTP expiry, rate limits, email templates, or delivery
  providers.
- Adding a new dependency, auth abstraction, or separate signup OTP screen.
- Automatically retrying verification or weakening Auth error handling.

### Definition of done

- [x] The cooldown visibly counts down and becomes an enabled `Resend code`
      action at sixty seconds.
- [x] Failed verification and successful resend clear the old code and focus
      Digit 1; the flow remains usable at mobile and desktop widths. A resend
      clicked before anything was typed also refocuses Digit 1
      (`CodeInput`'s new `resetSignal` prop, bumped alongside `resendAt`)
      since the cells being already-empty means `value` never changes.
- [x] Duplicate resend clicks produce one request and a fresh cooldown.
- [x] Auth/network failures are inline, recoverable, and do not discard the
      email address.
- [x] Deterministic mobile and desktop Playwright coverage passes alongside
      existing real GoTrue/Mailpit auth coverage: 12 new cases
      (`frontend/e2e/auth-otp-resend.spec.ts`,
      `frontend/e2e/mobile-auth-otp-resend.spec.ts`) plus the existing 19
      real-auth cases, all green.
- [x] Accessibility and visual-state review confirms disabled, loading,
      error, success, focus, and touch-target states use existing tokens and
      components. Also fixed the pre-existing "Wrong email?" control, found
      undersized (17px) once this ticket's mobile spec first checked `/login`
      at phone width - now `min-h-11` like the resend button and
      `Button.tsx`'s own `md` size.

## Whole-phase verification

Run the focused auth tests, frontend lint, typecheck, and relevant Playwright
tests for each branch. W-13 requires the authenticated hosted operational
check; W-12 requires both deterministic mocked coverage and the existing real
GoTrue/Mailpit path before its branch is merged.
