/**
 * W-12: OTP resend and retry recovery, phone width (iPhone 13, mobile-chrome
 * project). Same suite as auth-otp-resend.spec.ts; the mobile flag also
 * checks the 44px touch target and no horizontal overflow.
 */

import { otpResendSuite } from "./auth-helpers";

otpResendSuite({ mobile: true });
