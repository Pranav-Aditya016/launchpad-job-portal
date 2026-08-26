import type { ReactNode } from "react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div
      className="rounded-[var(--radius-card)] border-2 border-dashed border-[color:var(--border-strong)] p-1.5"
      style={{
        background: "var(--glass-bg)",
        backdropFilter: "blur(var(--glass-blur)) saturate(160%)",
        WebkitBackdropFilter: "blur(var(--glass-blur)) saturate(160%)",
      }}
    >
      <div className="glass-scrim flex flex-col items-center gap-3 px-8 py-16 text-center">
        {icon && <div className="text-muted opacity-70">{icon}</div>}
        <p className="font-display text-headline">{title}</p>
        {description && <p className="text-body text-muted max-w-sm">{description}</p>}
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  );
}
