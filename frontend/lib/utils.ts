export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

// Mirrors backend/app/sources/experience.py::is_entry_level so the dashboard
// badge and the server's fresher_only filter agree on what "entry level" means.
const ENTRY_MARKERS = [
  "intern",
  "internship",
  "junior",
  "jr ",
  "jr.",
  "entry level",
  "entry-level",
  "new grad",
  "new-grad",
  "graduate",
  "associate",
  "trainee",
  "apprentice",
  "0-2 year",
  "0 to 2 year",
  "early career",
  "fresher",
  "campus",
];
const SENIOR_MARKERS = [
  "senior",
  "sr ",
  "sr.",
  "staff",
  "principal",
  "lead ",
  "manager",
  "director",
  "head of",
  "architect",
  "vp ",
  "vice president",
  "executive",
  "expert",
  "10+ year",
  "distinguished",
];

export function isEntryLevel(title: string): boolean {
  const t = title.toLowerCase();
  if (SENIOR_MARKERS.some((s) => t.includes(s))) return false;
  return ENTRY_MARKERS.some((e) => t.includes(e));
}

export type ScoreTone = "excellent" | "good" | "fair" | "poor";

export function scoreTone(score: number): ScoreTone {
  if (score >= 80) return "excellent";
  if (score >= 60) return "good";
  if (score >= 40) return "fair";
  return "poor";
}

export function relativeDate(iso: string | null): string | null {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return iso;
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}
