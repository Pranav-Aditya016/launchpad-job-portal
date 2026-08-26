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

// Backend contract: `Evaluation.score` is a 1-5 float, NOT a 0-100 percentage
// (see backend/app/evaluate/evaluator.py — the rubric prompt asks for
// "score (1-5 float)"). Keep this constant as the single source of truth for
// the scale so ScoreDial's arc math and this tone mapping can never drift
// apart the way they did before (dial divided by 100, tone thresholds were
// 80/60/40 — a perfect 5.0 rendered as a 5% red arc labeled "poor").
export const SCORE_MAX = 5;

export function scoreTone(score: number): ScoreTone {
  if (score >= 4.0) return "excellent";
  if (score >= 3.0) return "good";
  if (score >= 2.0) return "fair";
  return "poor";
}

// Some source adapters emit a raw Unix epoch (seconds) instead of ISO-8601 —
// e.g. arbeitnow's "1786632957" — which `new Date()` can't parse and would
// otherwise fall through to the raw-string fallback below, showing a
// ten-digit number as the "posted" badge. Detect that shape first.
const UNIX_SECONDS = /^\d{9,10}$/;

export function relativeDate(iso: string | null): string | null {
  if (!iso) return null;
  const then = UNIX_SECONDS.test(iso) ? new Date(Number(iso) * 1000) : new Date(iso);
  if (Number.isNaN(then.getTime())) return iso;
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}
