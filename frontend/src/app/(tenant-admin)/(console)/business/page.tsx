"use client";

import { RowLink } from "@/components/ui/RowLink";
import { ScreenTopbar } from "@/components/ui/ScreenTopbar";
import { Icon } from "@/components/ui/Icon";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { useAuth } from "@/components/AuthProvider";

/**
 * E-1 / D21: Business, the third tab - a hub of places, built from
 * `renderScreen('business')` in agencx-prototype-v6.html (`.bh-row`: icon,
 * label, chevron). The hub shape is the point: Stage 2 adds Schedule, Money
 * and Plan as rows here, so growth costs a row rather than a re-cut of the
 * navigation.
 *
 * The page stays intentionally shallow: page presentation, offers, and the
 * supporting business details are distinct jobs, while sign-out remains a
 * single action rather than becoming a misleading account settings screen.
 *
 * Sign-out lives here because the hamburger drawer that used to hold it is
 * gone (E-1): on a phone the sidebar never renders, and sign-out must stay
 * reachable.
 */
export default function BusinessPage() {
  const { signOut } = useAuth();
  const { confirm: confirmSignOut, dialog: signOutDialog } = useConfirm();
  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-surface">
      <ScreenTopbar title="Business" back={false} />
      <div className="min-h-0 flex-1 overflow-y-auto lg:mx-auto lg:w-full lg:max-w-thread">
        <RowLink
          href="/business/page"
          label="Business page"
          icon="arrow_forward"
          detail="What customers see and how it looks"
        />
        <RowLink
          href="/business/offerings"
          label="What you offer"
          icon="sell"
          detail="The services and prices shown on your page"
        />
        <RowLink
          href="/business/details"
          label="Business details"
          icon="settings"
          detail="Knowledge, ABN, and tax details"
        />
        <button
          type="button"
          onClick={() =>
            void confirmSignOut({
              title: "Sign out?",
              description: "You will need your email code to sign back in.",
              confirmLabel: "Sign out",
              onConfirm: () => signOut(),
            })
          }
          className="flex w-full items-center gap-3.5 border-b border-hairline px-gutter py-[15px] text-left transition-colors duration-(--duration-fast) hover:bg-surface-container active:bg-ink-a05 lg:hidden"
        >
          <span className="flex size-5 shrink-0 items-center justify-center text-ink-a40">
            <Icon name="logout" size={20} />
          </span>
          <span className="flex-1 text-row-label font-medium text-text">Sign out</span>
        </button>
      </div>
      {signOutDialog}
    </main>
  );
}
