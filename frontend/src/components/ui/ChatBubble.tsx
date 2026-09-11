import type { ReactNode } from "react";

export type ChatRole = "customer" | "assistant" | "human_agent" | "system";

/**
 * Who is reading. On the customer surface the customer is the outbound voice;
 * in the owner's Chats thread the business is, and the customer's messages
 * arrive. Same roles, mirrored sides - C-6.
 */
export type ChatPerspective = "customer" | "operator";

export interface ChatBubbleProps {
  role: ChatRole;
  perspective?: ChatPerspective;
  /**
   * What to call the person behind a `human_agent` bubble, customer-side. The
   * customer surface passes the tenant's own name ("Bytefix staff") because the
   * page is branded as that business and "a human agent" is neither what the
   * customer sees themselves talking to nor a phrase PRD section 13 allows -
   * `\bagents?\b` is banned in customer copy. The default covers the surfaces
   * that render a transcript without a tenant name to hand.
   */
  senderLabel?: string;
  children: ReactNode;
}

const ROLE_CLASSES: Record<ChatPerspective, Record<ChatRole, string>> = {
  customer: {
    customer: "self-end bg-bubble-out text-text-inverse",
    assistant: "self-start bg-bubble-in text-text",
    human_agent: "self-start bg-bubble-agent-in text-text",
    system: "self-center bg-transparent text-text-tertiary text-footnote",
  },
  operator: {
    // The business is the outbound voice here. The assistant's answers and the
    // owner's own replies look the same, exactly as the prototype's operator
    // thread has them - the takeover stamp is what marks who was speaking, and
    // it reads better than labelling every bubble.
    customer: "self-start bg-bubble-in text-text",
    assistant: "self-end bg-bubble-out text-text-inverse",
    human_agent: "self-end bg-bubble-out text-text-inverse",
    system: "self-center bg-transparent text-text-tertiary text-footnote",
  },
};

// The 4px corner always points at the speaker: inbound tips top-left,
// outbound tips top-right. Which role is which depends on who is reading.
const INBOUND =
  "rounded-[var(--radius-bubble-tip)_var(--radius-bubble)_var(--radius-bubble)_var(--radius-bubble)]";
const OUTBOUND =
  "rounded-[var(--radius-bubble)_var(--radius-bubble-tip)_var(--radius-bubble)_var(--radius-bubble)]";

const RADIUS_CLASSES: Record<ChatPerspective, Record<ChatRole, string>> = {
  customer: {
    customer: OUTBOUND,
    assistant: INBOUND,
    human_agent: INBOUND,
    system: "",
  },
  operator: {
    customer: INBOUND,
    assistant: OUTBOUND,
    human_agent: OUTBOUND,
    system: "",
  },
};

/**
 * docs/agencx/design/frontend.md section 6: owner/customer bubbles (filled, right)
 * (filled, right) with a top-right tip, assistant bubbles (light, left) with a
 * top-left tip, human_agent (blossom, labeled with senderLabel), system (centered
 * caption). Streaming arrives with StreamingText.
 */
export function ChatBubble({
  role,
  perspective = "customer",
  senderLabel = "Business staff",
  children,
}: ChatBubbleProps) {
  if (role === "system") {
    return (
      <p className={`w-full text-center ${ROLE_CLASSES[perspective].system}`}>{children}</p>
    );
  }

  return (
    <div
      className={`max-w-[85%] px-4 py-2.5 text-body-sm leading-relaxed ${RADIUS_CLASSES[perspective][role]} ${ROLE_CLASSES[perspective][role]}`}
    >
      {role === "human_agent" && perspective === "customer" ? (
        <p className="mb-1 text-footnote font-medium text-accent-active">{senderLabel}</p>
      ) : null}
      {children}
    </div>
  );
}
