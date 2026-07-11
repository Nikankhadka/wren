import type { ReactNode } from "react";

export interface StreamingTextProps {
  streaming: boolean;
  children: ReactNode;
}

/**
 * docs/design/frontend.md section 6: renders SSE tokens with a caret pulse
 * while streaming; `aria-live="polite"` so assistive tech announces new
 * text without interrupting. Interrupted/retry is the caller's concern
 * (rendered as a sibling affordance in the bubble, not by this component).
 */
export function StreamingText({ streaming, children }: StreamingTextProps) {
  return (
    <span aria-live="polite">
      {children}
      {streaming ? (
        <span
          className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-text align-middle"
          aria-hidden="true"
        />
      ) : null}
    </span>
  );
}
