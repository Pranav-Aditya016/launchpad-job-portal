"use client";

import { useRef, useState, type DragEvent } from "react";
import { cn } from "@/lib/utils";

interface DropzoneProps {
  onFile: (file: File) => void;
  accept?: string;
  disabled?: boolean;
}

export function Dropzone({ onFile, accept = ".pdf,.docx,.doc,.txt", disabled }: DropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    const file = e.dataTransfer.files?.[0];
    if (file) onFile(file);
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed px-8 py-16 text-center transition-[border-color,background-color,transform] duration-200",
        dragging
          ? "border-accent bg-[color:var(--accent-wash)] scale-[1.01]"
          : "border-[color:var(--border-strong)] hover:bg-surface-2",
        disabled && "pointer-events-none opacity-50"
      )}
    >
      <div
        className="flex h-14 w-14 items-center justify-center rounded-full"
        style={{ background: "var(--accent-wash)" }}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 16V4M12 4l-4 4M12 4l4 4" />
          <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
        </svg>
      </div>
      <p className="text-headline">Drop your resume here</p>
      <p className="text-body text-muted">or click to browse — PDF, DOCX, or TXT</p>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}
