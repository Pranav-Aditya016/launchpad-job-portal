import { cn } from "@/lib/utils";

export type ConnectionStatus = "disconnected" | "connected" | "expired" | "checking" | "blocked";

const STATUS_COLOR: Record<ConnectionStatus, string> = {
  disconnected: "var(--muted)",
  connected: "var(--success)",
  expired: "var(--warning)",
  checking: "var(--accent)",
  blocked: "var(--danger)",
};

export const STATUS_LABEL: Record<ConnectionStatus, string> = {
  disconnected: "Not connected",
  connected: "Connected",
  expired: "Session expired",
  checking: "Checking…",
  blocked: "Blocked",
};

interface StatusDotProps {
  status: ConnectionStatus;
  className?: string;
}

// Color alone never carries the meaning — every caller pairs this with
// STATUS_LABEL as visible text (see ConnectionCard), so this dot is a
// decorative accent, not the sole signal.
export function StatusDot({ status, className }: StatusDotProps) {
  const color = STATUS_COLOR[status];
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block h-2.5 w-2.5 shrink-0 rounded-full",
        status === "checking" && "status-dot--pulse",
        className
      )}
      style={{ background: color }}
    />
  );
}
