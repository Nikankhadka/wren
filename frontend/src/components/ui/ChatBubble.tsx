import type { ReactNode } from "react";

export type ChatRole = "customer" | "assistant" | "human_agent" | "system";

export interface ChatBubbleProps {
  role: ChatRole;
  children: ReactNode;
}

const ROLE_CLASSES: Record<ChatRole, string> = {
  customer: "self-end bg-accent-subtle text-text",
  assistant: "self-start bg-surface text-text border border-border",
  human_agent: "self-start bg-info-subtle text-text",
  system: "self-center bg-transparent text-text-tertiary text-footnote",
};

/**
 * docs/design/frontend.md section 6: customer (accent-subtle, right),
 * assistant (surface, left), human_agent (info-subtle, labeled), system
 * (centered caption). Static only for now - streaming arrives with
 * StreamingText in T-011.
 */
export function ChatBubble({ role, children }: ChatBubbleProps) {
  if (role === "system") {
    return <p className={`w-full text-center ${ROLE_CLASSES.system}`}>{children}</p>;
  }

  return (
    <div
      className={`max-w-[85%] rounded-lg px-4 py-2.5 text-body-sm leading-relaxed ${ROLE_CLASSES[role]}`}
    >
      {role === "human_agent" ? (
        <p className="mb-1 text-footnote font-medium text-text-secondary">Human agent</p>
      ) : null}
      {children}
    </div>
  );
}
