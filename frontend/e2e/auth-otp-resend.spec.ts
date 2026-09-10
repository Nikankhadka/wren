/**
 * W-12: OTP resend and retry recovery, desktop. The suite itself lives in
 * auth-helpers.ts (`otpResendSuite`) so it can run identically under the
 * mobile-chrome project too (mobile-auth-otp-resend.spec.ts).
 */

import { otpResendSuite } from "./auth-helpers";

otpResendSuite({ mobile: false });
