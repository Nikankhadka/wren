"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Badge, toneForStatus } from "@/components/ui/Badge";
import { ChatBubble, type ChatRole } from "@/components/ui/ChatBubble";
import { EmptyState } from "@/components/ui/EmptyState";
import { TraceTree, type TraceToolCall, type TraceCheckVerdict } from "@/components/ui/TraceTree";
import { apiFetch, ApiError } from "@/lib/api";
import { formatUsd } from "@/lib/money";

interface MessageDetail {
  id: string;
  role: string;
  content: string;
  agent_node: string | null;
  created_at: string;
  metadata: { inspection?: Record<string, TraceCheckVerdict> } & Record<string, unknown>;
  cost_usd: number | null;
  tool_calls: TraceToolCall[];
}

interface ConversationDetail {
  id: string;
  customer_ref: string | null;
  channel: string;
  status: string;
  created_at: string;
  total_cost_usd: number;
  messages: MessageDetail[];
}

const CHAT_ROLES: ReadonlySet<string> = new Set([
  "customer",
  "assistant",
  "human_agent",
  "system",
]);

function toChatRole(role: string): ChatRole {
  return CHAT_ROLES.has(role) ? (role as ChatRole) : "system";
}

/**
 * T-031: conversation detail (frontend.md 7.2). Full transcript as ChatBubbles
 * with a per-message TraceTree under each assistant message; total cost in the
 * header. A 404 (not found or cross-tenant) shows a calm not-found state.
 */
export default function ConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let active = true;
    apiFetch<ConversationDetail>(`/api/conversations/${id}`)
      .then((data) => {
        if (!active) return;
        setConversation(data);
        setError(null);
        setNotFound(false);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(err instanceof ApiError ? err.detail : "Failed to load conversation");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="flex flex-col gap-3 p-8">
        <div className="h-6 w-48 animate-pulse rounded bg-surface-sunken" />
        <div className="h-4 w-64 animate-pulse rounded bg-surface-sunken" />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="p-8">
        <EmptyState
          title="Conversation not found"
          description="It may have been removed, or it belongs to a different business."
          action={
            <Link
              href="/conversations"
              className="text-body-sm font-medium text-accent hover:text-accent-hover"
            >
              Back to conversations
            </Link>
          }
        />
      </div>
    );
  }

  if (error || !conversation) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-border bg-surface p-6 text-body-sm text-danger">
          {error ?? "Failed to load conversation"}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-8">
      <div className="flex flex-col gap-2">
        <Link
          href="/conversations"
          className="text-footnote font-medium text-accent hover:text-accent-hover"
        >
          &larr; Conversations
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-title-2 font-semibold text-text">
            {conversation.customer_ref ?? "Anonymous"}
          </h1>
          <Badge tone={toneForStatus(conversation.status)}>{conversation.status}</Badge>
          <span className="text-body-sm text-text-secondary">
            Total cost{" "}
            <span className="font-medium tabular-nums text-text">
              {formatUsd(conversation.total_cost_usd)}
            </span>
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {conversation.messages.map((message) => {
          const role = toChatRole(message.role);
          return (
            <div key={message.id} className="flex flex-col gap-1">
              <ChatBubble role={role}>{message.content}</ChatBubble>
              {role === "assistant" ? (
                <div className="max-w-[85%] self-start">
                  <TraceTree
                    agentNode={message.agent_node}
                    costUsd={message.cost_usd}
                    toolCalls={message.tool_calls}
                    inspection={message.metadata?.inspection}
                  />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
