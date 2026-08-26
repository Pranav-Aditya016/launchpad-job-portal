import { STATUS_LABEL, STATUS_SOLID, type DisplayStatus } from "@/components/StatusBadge";

export interface CoverageSegment {
  status: DisplayStatus;
  count: number;
}

interface CoverageBarProps {
  segments: CoverageSegment[];
}

// The signature transparency visual: one glance answers "how many sources
// exist, and what state is each one in" — a segmented bar (never a single
// number) because collapsing five different meanings into one score is
// exactly the blur the handoff spec warns against.
export function CoverageBar({ segments }: CoverageBarProps) {
  const total = segments.reduce((sum, s) => sum + s.count, 0);
  const present = segments.filter((s) => s.count > 0);

  if (total === 0) {
    return (
      <div className="h-3 w-full rounded-full bg-surface-2" aria-hidden="true" />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        className="flex h-3 w-full overflow-hidden rounded-full bg-surface-2"
        role="img"
        aria-label={present.map((s) => `${STATUS_LABEL[s.status]}: ${s.count}`).join(", ")}
      >
        {present.map((s, i) => (
          <div
            key={s.status}
            style={{
              width: `${(s.count / total) * 100}%`,
              background: STATUS_SOLID[s.status],
            }}
            className={i > 0 ? "border-l border-[color:var(--glass-bg)]" : undefined}
            title={`${STATUS_LABEL[s.status]}: ${s.count}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {segments.map((s) => (
          <div key={s.status} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: STATUS_SOLID[s.status] }}
            />
            <span className="text-caption text-muted">
              {STATUS_LABEL[s.status]} · {s.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
