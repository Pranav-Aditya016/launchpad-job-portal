import { cn } from "@/lib/utils";

type Tone = "danger" | "warning" | "success" | "neutral" | "accent";

const TONE_CLASSES: Record<Tone, string> = {
  danger: "bg-[color:var(--danger-wash)] text-danger",
  warning: "bg-[color:var(--warning-wash)] text-warning",
  success: "bg-[color:var(--success-wash)] text-success",
  neutral: "bg-surface-2 text-muted",
  accent: "bg-[color:var(--accent-wash)] text-accent",
};

interface BadgeProps {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
}

export function Badge({ tone = "neutral", children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[0.75rem] font-semibold tracking-[0.01em] whitespace-nowrap",
        TONE_CLASSES[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
