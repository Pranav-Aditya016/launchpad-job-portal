"use client";

import { motion } from "motion/react";

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
}

// The thumb is a spring, not a CSS transition, so a rapid double-toggle
// re-targets smoothly instead of restarting a keyframe from the top.
export function Toggle({ checked, onChange, label, description }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-4 rounded-xl px-1 py-1.5 text-left"
    >
      <span className="flex flex-col">
        <span className="text-body font-medium text-foreground">{label}</span>
        {description && <span className="text-caption text-muted">{description}</span>}
      </span>
      <span
        className="relative inline-flex h-[26px] w-[46px] shrink-0 items-center rounded-full transition-colors duration-200"
        style={{ background: checked ? "var(--accent)" : "var(--border-strong)" }}
      >
        <motion.span
          className="block h-[22px] w-[22px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.3)]"
          animate={{ x: checked ? 22 : 2 }}
          transition={{ type: "spring", bounce: 0, duration: 0.3 }}
        />
      </span>
    </button>
  );
}
