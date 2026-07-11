import type { ReactNode } from "react";

export interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
}

/**
 * docs/design/frontend.md section 6: icon + one-line explanation + primary
 * action - never a bare "No data". No icon set exists yet, so a plain
 * accent dot stands in until one is chosen.
 */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <span className="h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
      <p className="text-body font-medium text-text">{title}</p>
      <p className="max-w-sm text-body-sm text-text-secondary">{description}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
