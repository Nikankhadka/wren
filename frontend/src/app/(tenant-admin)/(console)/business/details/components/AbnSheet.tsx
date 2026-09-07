"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Sheet } from "@/components/ui/Sheet";
import { formatAbn, isGstRegistered, NO_ABN } from "@/lib/abn";
import type { BusinessProfile, ProfileUpdate } from "@/lib/api-schemas";

export interface AbnSheetProps {
  open: boolean;
  profile: BusinessProfile;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (update: ProfileUpdate) => void;
}

/**
 * The prototype's "ABN & Tax" edit sheet (`openSettingsEdit('abn')`): the
 * masked number, and whether the business is registered for GST.
 *
 * One deviation from the prototype, recorded with O-5's list: GST is a chip
 * pair here, not the prototype's `se_toggleField` switch. It is the same
 * question the interview asks, with the same control the interview asks it
 * with, and it saves adding a switch primitive to the system for one boolean.
 */
export function AbnSheet({ open, profile, busy, error, onClose, onSave }: AbnSheetProps) {
  return (
    <Sheet open={open} onClose={onClose} title="Edit ABN & Tax">
      {/* Keyed by what was loaded: reopening starts from what is saved, so an
          abandoned edit is not still sitting there next time. */}
      {open ? (
        <AbnEditor
          key={`${profile.abn}:${profile.gst}`}
          profile={profile}
          busy={busy}
          error={error}
          onSave={onSave}
        />
      ) : null}
    </Sheet>
  );
}

function AbnEditor({
  profile,
  busy,
  error,
  onSave,
}: {
  profile: BusinessProfile;
  busy: boolean;
  error: string | null;
  onSave: (update: ProfileUpdate) => void;
}) {
  // "none" is the stated "I do not have one" - an empty field, not the word.
  const [abn, setAbn] = useState(() =>
    profile.abn.trim().toLowerCase() === NO_ABN ? "" : formatAbn(profile.abn),
  );
  const [gst, setGst] = useState(() => isGstRegistered(profile.gst));
  const digits = abn.replace(/\D/g, "");

  return (
    <div className="flex flex-col gap-[18px] pb-2">
      <label className="block">
        <span className="mb-2 block text-field-label font-medium uppercase text-ink-a40">ABN</span>
        <input
          value={abn}
          onChange={(event) => setAbn(formatAbn(event.target.value))}
          inputMode="numeric"
          type="tel"
          placeholder="XX XXX XXX XXX"
          autoFocus
          data-testid="abn-input"
          className="w-full rounded-field border-[length:var(--border-chip)] border-transparent bg-surface-container px-[18px] py-3.5 text-field text-text outline-none transition-colors duration-(--duration-fast) placeholder:text-ink-a40 focus:border-accent-a35 focus:bg-accent-a06"
        />
      </label>

      {/* Only asked of a business that has an ABN - the same condition the
          interview's GST beat carries, so the two never disagree. */}
      {digits.length > 0 ? (
        <div>
          <span className="mb-2 block text-field-label font-medium uppercase text-ink-a40">
            GST registered
          </span>
          <div className="flex gap-2">
            <Chip
              label="Yes"
              selected={gst}
              disabled={busy}
              onClick={() => setGst(true)}
              data-testid="gst-yes"
            />
            <Chip
              label="Not yet"
              selected={!gst}
              disabled={busy}
              onClick={() => setGst(false)}
              data-testid="gst-no"
            />
          </div>
        </div>
      ) : (
        <p className="text-meta text-ink-a40">
          Leave it empty if you don&apos;t have one yet.
        </p>
      )}

      {error ? (
        <p role="alert" className="text-meta text-danger">
          {error}
        </p>
      ) : null}

      <Button
        className="w-full rounded-field py-4"
        loading={busy}
        onClick={() => onSave({ abn: digits, gst: gst ? "yes" : "no" })}
        data-testid="abn-save"
      >
        Save
      </Button>
    </div>
  );
}
