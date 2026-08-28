// Client-side job filtering for the dashboard. The list is already fetched
// in full (see app/dashboard/page.tsx), so every filter here runs in memory
// against that array rather than round-tripping to the backend — with
// ~850 jobs and growing, that's what keeps it feeling instant.

import type { CustomSite, Job, Source } from "@/lib/api";
import { daysSince, isEntryLevel, resolveSourceMeta } from "@/lib/utils";

export type DatePosted = "any" | "24h" | "3d" | "7d" | "30d";
export type SortKey = "score" | "newest" | "company";

export interface DashboardFilters {
  search: string;
  minScore: number;
  sources: string[]; // job.source values; empty = every source
  region: string; // "all" or a region code, "" meaning unspecified
  entryLevelOnly: boolean;
  sponsorshipOnly: boolean;
  hideScam: boolean;
  hideApplied: boolean;
  datePosted: DatePosted;
  sort: SortKey;
}

export const DEFAULT_FILTERS: DashboardFilters = {
  search: "",
  minScore: 0,
  sources: [],
  region: "all",
  entryLevelOnly: false,
  sponsorshipOnly: false,
  hideScam: false,
  hideApplied: false,
  datePosted: "any",
  sort: "score",
};

export const DATE_POSTED_OPTIONS: { value: DatePosted; label: string }[] = [
  { value: "any", label: "Any time" },
  { value: "24h", label: "Last 24h" },
  { value: "3d", label: "Last 3 days" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

export const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "score", label: "Best fit" },
  { value: "newest", label: "Newest" },
  { value: "company", label: "Company A–Z" },
];

const DATE_WINDOW_DAYS: Record<Exclude<DatePosted, "any">, number> = {
  "24h": 1,
  "3d": 3,
  "7d": 7,
  "30d": 30,
};

// posted comes from third-party feeds in inconsistent shapes (see
// relativeDate's Unix-seconds note); first_seen is always our own ISO-8601
// stamp, so prefer it and fall back to posted only when first_seen is
// missing on an older record.
function bestDate(job: Job): string | null {
  return job.first_seen ?? job.posted ?? null;
}

export function applyFilters(jobs: Job[], filters: DashboardFilters): Job[] {
  const q = filters.search.trim().toLowerCase();

  const filtered = jobs.filter((job) => {
    if (q) {
      const hay = `${job.title} ${job.company} ${job.location}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (filters.minScore > 0 && (!job.evaluation || job.evaluation.score < filters.minScore)) {
      return false;
    }
    if (filters.sources.length > 0 && !filters.sources.includes(job.source)) return false;
    if (filters.region !== "all" && (job.region ?? "") !== filters.region) return false;
    if (filters.entryLevelOnly && !isEntryLevel(job.title)) return false;
    if (filters.sponsorshipOnly && job.sponsorship_ok !== true) return false;
    if (filters.hideScam && job.evaluation?.scam_flag) return false;
    if (filters.hideApplied && job.applied) return false;
    if (filters.datePosted !== "any") {
      const days = daysSince(bestDate(job));
      if (days === null || days > DATE_WINDOW_DAYS[filters.datePosted]) return false;
    }
    return true;
  });

  return filtered.sort((a, b) => {
    if (filters.sort === "newest") {
      const da = daysSince(bestDate(a)) ?? Number.MAX_SAFE_INTEGER;
      const db = daysSince(bestDate(b)) ?? Number.MAX_SAFE_INTEGER;
      return da - db;
    }
    if (filters.sort === "company") {
      return a.company.localeCompare(b.company);
    }
    // "score" (default): unevaluated jobs sort after evaluated ones.
    return (b.evaluation?.score ?? -1) - (a.evaluation?.score ?? -1);
  });
}

export function isDefaultFilters(f: DashboardFilters): boolean {
  return (
    f.search === "" &&
    f.minScore === 0 &&
    f.sources.length === 0 &&
    f.region === "all" &&
    !f.entryLevelOnly &&
    !f.sponsorshipOnly &&
    !f.hideScam &&
    !f.hideApplied &&
    f.datePosted === "any" &&
    f.sort === "score"
  );
}

export interface SourceOption {
  key: string;
  label: string;
  kind: string;
  count: number;
}

// Grouped by resolved kind, each group's options sorted by how many jobs
// they actually contributed — the most useful filters float to the top of
// a list that (with 15 distinct sources) doesn't otherwise fit at a glance.
export function buildSourceOptions(
  jobs: Job[],
  sources: Source[],
  customSites: CustomSite[]
): Map<string, SourceOption[]> {
  const counts = new Map<string, number>();
  jobs.forEach((j) => counts.set(j.source, (counts.get(j.source) ?? 0) + 1));

  const options: SourceOption[] = Array.from(counts.entries()).map(([key, count]) => {
    const meta = resolveSourceMeta(key, sources, customSites);
    return { key, label: meta.label, kind: meta.kind, count };
  });
  options.sort((a, b) => b.count - a.count);

  const groups = new Map<string, SourceOption[]>();
  options.forEach((opt) => {
    const arr = groups.get(opt.kind) ?? [];
    arr.push(opt);
    groups.set(opt.kind, arr);
  });
  return groups;
}

export interface RegionChoice {
  code: string;
  label: string;
  count: number;
}

/**
 * The region filter's options: every region the app knows about, each with how
 * many of the current jobs sit in it.
 *
 * Deliberately driven by the canonical list rather than by the jobs on screen.
 * Deriving options from the data means a region vanishes from the filter the
 * moment it has no results — which is exactly the case where the user wants to
 * pick it and see "0" rather than wonder where it went.
 */
export function buildRegionOptions(
  jobs: Job[],
  canonical: { code: string; label: string }[],
): RegionChoice[] {
  const counts = new Map<string, number>();
  jobs.forEach((j) => {
    const c = j.region ?? "";
    counts.set(c, (counts.get(c) ?? 0) + 1);
  });

  const known = canonical.map((r) => ({
    code: r.code,
    label: r.label,
    count: counts.get(r.code) ?? 0,
  }));

  // Anything the backend didn't name still deserves a row rather than becoming
  // invisible and unfilterable.
  const extra = [...counts.keys()]
    .filter((c) => !canonical.some((r) => r.code === c))
    .map((c) => ({ code: c, label: c ? c.toUpperCase() : "Unspecified", count: counts.get(c) ?? 0 }));

  return [...known, ...extra];
}
