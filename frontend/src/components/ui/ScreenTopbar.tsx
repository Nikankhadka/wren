"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { Icon } from "./Icon";

export interface ScreenTopbarProps {
  title: string;
  /** Where back goes. Omit to pop the history stack (the prototype's navBack). */
  backHref?: string;
  /**
   * False on a top-level tab destination, which is not a place you came from.
   * The prototype has both variants: a `.bk-btn` on a pushed screen, and a
   * bare 36px spacer on the ones its tab bar owns.
   */
  back?: boolean;
  /** Trailing slot - the prototype puts a close or an action glyph here. */
  action?: ReactNode;
}

/**
 * The prototype's `.dst-topbar`: a 58px bar with a back control, a centred-weight
 * title, and an optional trailing action, over a hairline rule. Every
 * destination screen in agencx-prototype-v6.html opens with this - it is what
 * makes a screen feel like a place you can leave, which matters most on a phone
 * where there is no sidebar to fall back to.
 */
export function ScreenTopbar({ title, backHref, back = true, action }: ScreenTopbarProps) {
  const router = useRouter();
  return (
    <header className="flex h-topbar shrink-0 items-center justify-between border-b border-hairline px-5 pb-3.5 pt-4">
      {back ? (
        <button
          type="button"
          aria-label="Back"
          onClick={() => (backHref ? router.push(backHref) : router.back())}
          // Drawn as the prototype's 36px glyph button, but sized to the 44px
          // touch floor frontend.md sets, with the extra 8px pulled back out as
          // negative margin. The box a thumb hits grows; the arrow does not
          // move, and neither does the title beside it.
          className="-ml-3 -mr-1 flex size-icon-btn-hit items-center justify-center rounded-full text-text active:opacity-60"
        >
          <Icon name="arrow_back" size={20} />
        </button>
      ) : (
        <span className="size-icon-btn" />
      )}
      <span className="text-screen-title font-medium text-text">{title}</span>
      <span className="flex size-icon-btn items-center justify-center">{action}</span>
    </header>
  );
}
