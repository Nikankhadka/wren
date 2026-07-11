"use client";

import { useRef, useState, type DragEvent, type KeyboardEvent } from "react";

export interface FileDropzoneProps {
  accept: string;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
}

/**
 * docs/design/frontend.md section 6: idle, drag-over, disabled. Per-file
 * upload progress / done / rejected is the caller's list to render below
 * the dropzone (this component is just the drop/browse surface).
 */
export function FileDropzone({ accept, disabled, onFiles }: FileDropzoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function openBrowser() {
    if (!disabled) inputRef.current?.click();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openBrowser();
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    if (disabled) return;
    onFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
      onClick={openBrowser}
      onKeyDown={handleKeyDown}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={[
        "flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2",
        "border-dashed p-8 text-center transition-colors duration-fast",
        dragOver ? "border-accent bg-accent-subtle" : "border-border bg-surface-sunken",
        disabled ? "pointer-events-none opacity-50" : "",
      ].join(" ")}
    >
      <p className="text-body-sm font-medium text-text">Drop a file here, or click to browse</p>
      <p className="text-footnote text-text-secondary">Accepted: {accept}</p>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        disabled={disabled}
        className="hidden"
        onChange={(event) => {
          if (event.target.files) onFiles(Array.from(event.target.files));
          event.target.value = "";
        }}
      />
    </div>
  );
}
