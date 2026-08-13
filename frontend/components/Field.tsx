"use client";

import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const fieldChrome =
  "w-full rounded-xl border border-[color:var(--border-strong)] bg-surface px-3.5 py-2.5 " +
  "text-[0.9375rem] text-foreground placeholder:text-muted outline-none " +
  "transition-[box-shadow,border-color] duration-150 " +
  "focus:border-accent focus:ring-4 focus:ring-[color:var(--accent-wash)]";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(
  ({ label, hint, id, className, ...props }, ref) => {
    const inputId = id ?? `field-${label.replace(/\s+/g, "-").toLowerCase()}`;
    return (
      <label htmlFor={inputId} className="flex flex-col gap-1.5">
        <span className="text-caption text-muted">{label}</span>
        <input ref={ref} id={inputId} className={cn(fieldChrome, className)} {...props} />
        {hint && <span className="text-caption text-muted">{hint}</span>}
      </label>
    );
  }
);
Field.displayName = "Field";

interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  hint?: string;
}

export const TextAreaField = forwardRef<HTMLTextAreaElement, TextAreaFieldProps>(
  ({ label, hint, id, className, ...props }, ref) => {
    const inputId = id ?? `field-${label.replace(/\s+/g, "-").toLowerCase()}`;
    return (
      <label htmlFor={inputId} className="flex flex-col gap-1.5">
        <span className="text-caption text-muted">{label}</span>
        <textarea ref={ref} id={inputId} className={cn(fieldChrome, "resize-y", className)} {...props} />
        {hint && <span className="text-caption text-muted">{hint}</span>}
      </label>
    );
  }
);
TextAreaField.displayName = "TextAreaField";

interface TagListFieldProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  hint?: string;
}

// Comma/enter-separated tag editor for list fields (skills, target_roles, proof_points)
// — keeps the profile-review card editable without a heavier chip-input dependency.
export function TagListField({ label, values, onChange, placeholder, hint }: TagListFieldProps) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-caption text-muted">{label}</span>
      <textarea
        className={cn(fieldChrome, "resize-y min-h-20")}
        value={values.join("\n")}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value.split("\n").map((v) => v.trim()).filter(Boolean))}
      />
      {hint && <span className="text-caption text-muted">{hint}</span>}
    </label>
  );
}
