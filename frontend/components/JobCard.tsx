import Link from "next/link";
import type { Job } from "@/lib/api";
import { isEntryLevel, relativeDate } from "@/lib/utils";
import { Badge } from "@/components/Badge";
import { ScoreDial } from "@/components/ScoreDial";

interface JobCardProps {
  job: Job;
}

export function JobCard({ job }: JobCardProps) {
  const ev = job.evaluation;
  const entryLevel = isEntryLevel(job.title);
  const posted = relativeDate(job.posted);

  return (
    <Link
      href={`/job/${job.id}`}
      className="pressable group flex items-start gap-4 rounded-2xl border border-[color:var(--border)] bg-surface p-5 shadow-[var(--shadow-card)] transition-[box-shadow,border-color] duration-200 hover:border-[color:var(--border-strong)] hover:shadow-[var(--shadow-elevated)]"
    >
      {ev ? (
        <ScoreDial score={ev.score} />
      ) : (
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-dashed border-[color:var(--border-strong)] text-caption text-muted">
          —
        </div>
      )}

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-headline truncate">{job.title}</h3>
        </div>
        <p className="text-body text-muted truncate">
          {job.company}
          {job.location && <> · {job.location}</>}
        </p>

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          {ev?.scam_flag && <Badge tone="danger">Possible scam</Badge>}
          {ev?.no_sponsorship && <Badge tone="warning">No sponsorship</Badge>}
          {job.sponsorship_ok === true && (
            <Badge tone="neutral">Sponsorship likely OK</Badge>
          )}
          {entryLevel && <Badge tone="success">Entry level</Badge>}
          {job.applied && <Badge tone="accent">Applied</Badge>}
          <Badge tone="neutral">{job.source}</Badge>
          {posted && <span className="text-caption text-muted">{posted}</span>}
        </div>

        {ev?.summary && (
          <p className="mt-2 text-body text-muted line-clamp-2">{ev.summary}</p>
        )}
      </div>
    </Link>
  );
}
