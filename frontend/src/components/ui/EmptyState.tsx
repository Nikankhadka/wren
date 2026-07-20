import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
  /** Material Symbol shown in an accent chip above the title. */
  icon?: IconName;
}

/**
 * docs/design/frontend.md section 6: icon + one-line explanation + primary
 * action - never a bare "No data". Callers that pass an `icon` get it in an
 * accent chip; the rest fall back to a plain accent dot.
 */
export function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      {icon ? (
        <span
          className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-subtle text-accent"
          aria-hidden="true"
        >
          <Icon name={icon} size={22} />
        </span>
      ) : (
        <span className="h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
      )}
      <p className="text-body font-medium text-text">{title}</p>
      <p className="max-w-sm text-body-sm text-text-secondary">{description}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
