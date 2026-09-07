"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Sheet } from "@/components/ui/Sheet";
import type { BusinessProfile, ProfileUpdate } from "@/lib/api-schemas";

/** The owner's own description, bounded (backend `CUSTOM_VOICE_MAX`). */
const CUSTOM_VOICE_MAX = 300;
const CUSTOM = "custom";

/** The four voices, in the order the interview's own chips offer them. */
const VOICES: { value: string; label: string; help: string }[] = [
  { value: "warm_casual", label: "Warm and casual", help: "Friendly, everyday words." },
  { value: "clear_professional", label: "Clear and professional", help: "Plain, courteous, no slang." },
  { value: "direct_concise", label: "Direct and concise", help: "Short sentences, no filler." },
  { value: CUSTOM, label: "In my own words", help: "Describe how it should sound." },
];

/**
 * The settings row's summary line: the voice as it would be described back.
 * A custom voice shows the owner's own words, shortened to one quiet line.
 */
export function voiceSummary(profile: BusinessProfile): string {
  const chosen = VOICES.find((voice) => voice.value === profile.customer_voice_preset);
  if (chosen && chosen.value !== CUSTOM) return chosen.label;
  const style = profile.customer_voice_custom_style.trim();
  if (!style) return VOICES[0].label;
  return style.length > 60 ? `${style.slice(0, 60).trimEnd()}…` : style;
}

export interface VoiceSheetProps {
  open: boolean;
  profile: BusinessProfile;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (update: ProfileUpdate) => void;
}

/**
 * W-9 US-7: how the public assistant sounds. The same edit sheet the ABN row
 * opens, with the interview's own voice chips inside it - the choice is
 * expression only, and the code-owned contract (`app/agents/contract.py`) still
 * decides what the assistant may say.
 */
export function VoiceSheet({ open, profile, busy, error, onClose, onSave }: VoiceSheetProps) {
  return (
    <Sheet open={open} onClose={onClose} title="Edit assistant voice">
      {/* Keyed by what was loaded: reopening starts from what is saved, so an
          abandoned edit is not still sitting there next time. */}
      {open ? (
        <VoiceEditor
          key={`${profile.customer_voice_preset}:${profile.customer_voice_custom_style}`}
          profile={profile}
          busy={busy}
          error={error}
          onSave={onSave}
        />
      ) : null}
    </Sheet>
  );
}

function VoiceEditor({
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
  const [preset, setPreset] = useState(
    () => VOICES.find((voice) => voice.value === profile.customer_voice_preset)?.value ?? VOICES[0].value,
  );
  const [style, setStyle] = useState(() => profile.customer_voice_custom_style);
  // Raised on save rather than while typing: the field starts empty for every
  // owner choosing "In my own words", and that is not yet a mistake.
  const [missing, setMissing] = useState(false);
  const chosen = VOICES.find((voice) => voice.value === preset) ?? VOICES[0];
  const message = missing ? "Describe how you want your assistant to sound." : error;

  return (
    <div className="flex flex-col gap-[18px] pb-2">
      <div>
        <span className="mb-2 block text-field-label font-medium uppercase text-ink-a40">Voice</span>
        <div className="flex flex-wrap gap-2">
          {VOICES.map((voice) => (
            <Chip
              key={voice.value}
              label={voice.label}
              selected={preset === voice.value}
              disabled={busy}
              onClick={() => {
                setPreset(voice.value);
                setMissing(false);
              }}
              data-testid={`voice-${voice.value}`}
            />
          ))}
        </div>
        <p className="mt-2 text-meta text-ink-a40">{chosen.help}</p>
      </div>

      {preset === CUSTOM ? (
        <label className="block">
          <span className="mb-2 block text-field-label font-medium uppercase text-ink-a40">
            In your own words
          </span>
          <textarea
            value={style}
            onChange={(event) => {
              setStyle(event.target.value);
              setMissing(false);
            }}
            rows={3}
            maxLength={CUSTOM_VOICE_MAX}
            placeholder="Calm and reassuring, never pushy."
            autoFocus
            data-testid="voice-style"
            className="w-full resize-none rounded-field border-[length:var(--border-chip)] border-transparent bg-surface-container px-[18px] py-3.5 text-field text-text outline-none transition-colors duration-(--duration-fast) placeholder:text-ink-a40 focus:border-accent-a35 focus:bg-accent-a06"
          />
          <span className="mt-2 block text-meta text-ink-a40">
            {style.length}/{CUSTOM_VOICE_MAX} characters. It changes wording only, never a price, a
            policy, or when a person is brought in.
          </span>
        </label>
      ) : null}

      {message ? (
        <p role="alert" className="text-meta text-danger">
          {message}
        </p>
      ) : null}

      <Button
        className="w-full rounded-field py-4"
        loading={busy}
        onClick={() => {
          if (preset === CUSTOM && !style.trim()) {
            setMissing(true);
            return;
          }
          onSave({
            customer_voice_preset: preset,
            customer_voice_custom_style: preset === CUSTOM ? style.trim() : "",
          });
        }}
        data-testid="voice-save"
      >
        Save
      </Button>
    </div>
  );
}
