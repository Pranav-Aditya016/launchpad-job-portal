import { Badge } from "@/components/Badge";
import type { SourceStatus } from "@/lib/api";

// One shared vocabulary for "what did this source do", used on the Sources
// page and in run-now results. Five real statuses, plus "not run yet" for a
// source that's enabled but has never appeared in a scan result — that is
// deliberately NOT the same thing as "disabled" or "error".
export type DisplayStatus = SourceStatus | "not_run";

const STATUS_LABEL: Record<DisplayStatus, string> = {
  ok: "OK",
  empty: "Empty",
  error: "Error",
  needs_login: "Needs login",
  disabled: "Disabled",
  skipped: "Skipped",
  not_run: "Not run yet",
};

const STATUS_TONE: Record<DisplayStatus, "success" | "neutral" | "danger" | "accent" | "warning"> = {
  ok: "success",
  empty: "neutral",
  error: "danger",
  needs_login: "accent",
  disabled: "warning",
  skipped: "neutral",
  not_run: "neutral",
};

// Solid (non-washed) colors for use outside Badge — the coverage bar segments
// and legend dots, where a translucent wash would be too faint against glass.
export const STATUS_SOLID: Record<DisplayStatus, string> = {
  ok: "var(--success)",
  empty: "var(--muted)",
  error: "var(--danger)",
  needs_login: "var(--accent)",
  disabled: "var(--warning)",
  skipped: "var(--muted)",
  not_run: "var(--border-strong)",
};

export { STATUS_LABEL };

interface StatusBadgeProps {
  status: DisplayStatus;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <Badge tone={STATUS_TONE[status]} className={className}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}
