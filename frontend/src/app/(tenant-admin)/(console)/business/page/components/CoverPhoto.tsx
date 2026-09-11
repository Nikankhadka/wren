"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "react-hot-toast";
import { Icon } from "@/components/ui/Icon";
import { apiFetch, apiFetchStream } from "@/lib/api";

/**
 * The cover photo well, ported from `.bk-photo-wrap` in
 * agencx-prototype-v6.html: a 200px band that is a tinted invitation while
 * empty and the photo itself once set, with the "Edit photo" pill in its
 * bottom-right corner either way.
 *
 * The file is resized here before it is sent. A phone camera produces 4MB+ of
 * pixels for a band that is 200px tall, and the bytes land in a Postgres row -
 * so the client does the one job it is uniquely able to do cheaply, and the
 * server's 2MB cap becomes a backstop rather than a wall the owner hits.
 */

const MAX_EDGE_PX = 1600;
const JPEG_QUALITY = 0.82;

export async function downscale(file: File): Promise<Blob> {
  // createImageBitmap decodes off the main thread; a browser without it (or a
  // file it cannot decode) falls through to sending the original, which the
  // server will accept or refuse on its own terms.
  if (typeof createImageBitmap !== "function") return file;
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    return file;
  }
  const scale = Math.min(
    1,
    MAX_EDGE_PX / Math.max(bitmap.width, bitmap.height),
  );
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return file;
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
  );
  return blob ?? file;
}

export interface CoverPhotoProps {
  hasCover: boolean;
  onChanged: () => void;
}

export function CoverPhoto({ hasCover, onChanged }: CoverPhotoProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [src, setSrc] = useState<string | null>(null);
  // Bumped on every save so the photo is refetched: the URL never changes, and
  // the browser would otherwise keep showing the one that was just replaced.
  const [version, setVersion] = useState(0);

  /**
   * The cover is served behind the owner's bearer token, which an <img src>
   * cannot send - so the bytes are fetched and handed to the tag as an object
   * URL. Revoked on replacement and on unmount; leaving them is a real leak on
   * a page the owner edits repeatedly.
   */
  useEffect(() => {
    // No synchronous reset here: `hasCover` gates the render below, so a stale
    // object URL is never shown, and clearing it eagerly would be a cascading
    // setState inside the effect.
    if (!hasCover) return;
    let url: string | null = null;
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiFetchStream("/api/business/cover");
        const blob = await res.blob();
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
      } catch {
        if (!cancelled) setSrc(null);
      }
    })();
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [hasCover, version]);

  async function upload(file: File) {
    setBusy(true);
    try {
      const body = new FormData();
      const resized = await downscale(file);
      body.append("file", resized, file.name);
      await apiFetch("/api/business/cover", { method: "PUT", body });
      setVersion((n) => n + 1);
      onChanged();
      toast.success("Cover photo updated");
    } catch {
      toast.error("That image could not be saved. Try a JPEG or PNG under 2MB.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        disabled={busy}
        aria-label={hasCover ? "Change cover photo" : "Add a cover photo"}
        data-testid="booking-cover"
        className="flex h-[200px] w-full flex-col items-center justify-center gap-2.5 overflow-hidden bg-accent-a09 transition-[filter] duration-(--duration-fast) hover:brightness-95 active:brightness-90"
      >
        {hasCover && src ? (
          /* eslint-disable-next-line @next/next/no-img-element --
             an object URL for bytes from our own authed API, not an asset
             next/image could fetch or optimise. */
          <img src={src} alt="" className="h-full w-full object-cover" />
        ) : (
          <>
            <span className="text-accent-a35">
              <Icon name="photo_camera" size={36} />
            </span>
            <span className="text-body-sm text-accent-a50">
              {busy
                ? "Adding…"
                : hasCover
                  ? "Loading…"
                  : "Tap to add a cover photo"}
            </span>
          </>
        )}
      </button>

      {hasCover ? (
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="absolute bottom-3 right-3 flex items-center gap-1.5 rounded-chip bg-scrim px-3 py-1.5 text-badge font-medium text-text-inverse transition-[filter] duration-(--duration-fast) hover:brightness-110 active:brightness-95"
        >
          <Icon name="edit" size={11} />
          {busy ? "Saving…" : "Edit photo"}
        </button>
      ) : null}

      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        data-testid="booking-cover-input"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) void upload(file);
        }}
      />
    </div>
  );
}
