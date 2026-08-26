"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Job } from "@/lib/api";
import { isEntryLevel, relativeDate } from "@/lib/utils";
import { Badge } from "@/components/Badge";
import { ScoreDial } from "@/components/ScoreDial";

interface JobCardProps {
  job: Job;
}

// Only http(s) is safe to hand to a plain <a target="_blank"> — job URLs
// originate from third-party feeds and markdown-link extraction, so a
// malformed feed value is not impossible. Mirrors app/job/[id]/page.tsx.
const SAFE_URL = /^https?:\/\//i;

// The whole card navigates to the detail page (div + role="link" rather than
// wrapping everything in a Next <Link>, so the "Original ↗" control below
// can be a real, independently-clickable anchor instead of an invalid
// anchor-inside-anchor).
export function JobCard({ job }: JobCardProps) {
  const router = useRouter();
  const ev = job.evaluation;
  const entryLevel = isEntryLevel(job.title);
  const posted = relativeDate(job.posted);

  return (
    <div
      role="link"
      tabIndex={0}
      onClick={() => router.push(`/job/${job.id}`)}
      onKeyDown={(e) => {
        if (e.key === "Enter") router.push(`/job/${job.id}`);
      }}
      className="pressable glass glass-hover block cursor-pointer p-1.5"
    >
      <div className="glass-scrim flex items-start gap-4 p-5">
        {ev ? (
          <ScoreDial score={ev.score} />
        ) : (
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-dashed border-[color:var(--border-strong)] text-caption text-muted">
            —
          </div>
        )}

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <Link
              href={`/job/${job.id}`}
              onClick={(e) => e.stopPropagation()}
              className="min-w-0"
            >
              <h3 className="font-display text-headline truncate hover:text-accent">{job.title}</h3>
            </Link>
            {SAFE_URL.test(job.url) && (
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="pressable shrink-0 text-caption font-medium text-accent hover:underline"
              >
                Original ↗
              </a>
            )}
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
            {job.region && <Badge tone="neutral">{job.region.toUpperCase()}</Badge>}
            {posted && <span className="text-caption text-muted">{posted}</span>}
          </div>

          {ev?.summary && (
            <p className="mt-2 text-body text-muted line-clamp-2">{ev.summary}</p>
          )}
        </div>
      </div>
    </div>
  );
}
