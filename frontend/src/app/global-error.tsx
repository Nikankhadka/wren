"use client";

import { useEffect } from "react";
import { Inter } from "next/font/google";
import "./globals.css";

// global-error replaces the root layout when the root itself throws, so it must
// bring its own <html>/<body>, styles, and font. It cannot render the shared
// ErrorRecovery component's Button reliably (that assumes the app shell), so it
// inlines a minimal, token-styled recovery UI.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en" className={`h-full antialiased ${inter.variable}`}>
      <body className="min-h-full flex flex-col">
        <main
          role="alert"
          className="flex flex-1 flex-col items-center justify-center gap-3 bg-bg px-6 text-center"
        >
          <p className="text-title-2 font-medium text-text">Something went wrong</p>
          <p className="max-w-sm text-body-sm text-text-secondary">
            The application hit an unexpected error. Please try again - if it keeps happening,
            refresh the page shortly.
          </p>
          <button
            type="button"
            onClick={() => unstable_retry()}
            className="mt-2 inline-flex items-center justify-center rounded-md border border-border bg-surface px-4 py-2 text-body font-medium text-text transition-colors duration-(--duration-fast) hover:bg-surface-sunken active:bg-surface-container-high"
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
