"use client";

import type { RunNowResponse } from "@/lib/api";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  ApiError,
  evaluate,
  getCustomSites,
  getJobs,
  getProfile,
  getSources,
  runNow,
  type CustomSite,
  type Job,
  type Profile,
  type Source,
} from "@/lib/api";
import { NavBar } from "@/components/NavBar";
import { Button } from "@/components/Button";
import { Toggle } from "@/components/Toggle";
import { Field } from "@/components/Field";
import { JobCard } from "@/components/JobCard";
import { EmptyState } from "@/components/EmptyState";
import { Badge } from "@/components/Badge";
import { GlassCard } from "@/components/GlassCard";
import { FilterPanel } from "@/components/FilterPanel";
import {
  applyFilters,
  buildRegionOptions,
  buildSourceOptions,
  DEFAULT_FILTERS,
  isDefaultFilters,
  type DashboardFilters,
} from "@/lib/filters";

// Filter state survives a reload — with ~850 jobs and growing, re-building a
// carefully narrowed view every visit would be the annoying part, not the
// filtering itself.
const FILTERS_STORAGE_KEY = "launchpad:dashboard-filters:v1";

export default function DashboardPage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [sources, setSources] = useState<Source[]>([]);
  const [customSites, setCustomSites] = useState<CustomSite[]>([]);
  const [scanning, setScanning] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [sinceDays, setSinceDays] = useState(7);
  const [fresherOnly, setFresherOnly] = useState(true);
  const [crawlCurated, setCrawlCurated] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [scanWarnings, setScanWarnings] = useState<string[]>([]);
  const [lastRun, setLastRun] = useState<RunNowResponse | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS);
  const [filtersLoaded, setFiltersLoaded] = useState(false);

  // Load persisted filters once, client-side only — guarded so a corrupt or
  // absent value never breaks the page, and never read during SSR (reading
  // it synchronously in render would mismatch the server-rendered HTML,
  // which always starts from DEFAULT_FILTERS). The `await null` mirrors the
  // await-before-setState shape this app's other bootstrap effects use.
  useEffect(() => {
    let ignore = false;
    async function bootstrap() {
      await null;
      if (ignore) return;
      try {
        const raw = window.localStorage.getItem(FILTERS_STORAGE_KEY);
        if (raw) setFilters({ ...DEFAULT_FILTERS, ...JSON.parse(raw) });
      } catch {
        // private browsing, corrupt value, etc. — fall back to defaults
      } finally {
        setFiltersLoaded(true);
      }
    }
    bootstrap();
    return () => {
      ignore = true;
    };
  }, []);

  // Persist on every change, once the initial load above has happened (so
  // we don't immediately overwrite a saved value with the pre-load default).
  useEffect(() => {
    if (!filtersLoaded) return;
    try {
      window.localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(filters));
    } catch {
      // ignore — best-effort persistence only
    }
  }, [filters, filtersLoaded]);

  function updateFilters(patch: Partial<DashboardFilters>) {
    setFilters((cur) => ({ ...cur, ...patch }));
  }

  const loadJobs = useCallback(async () => {
    setJobsLoading(true);
    try {
      const data = await getJobs();
      setJobs(data);
    } catch (e) {
      setErrorMessage(e instanceof ApiError ? e.message : "Couldn't load jobs.");
    } finally {
      setJobsLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    async function bootstrap() {
      // Sources/custom-sites are best-effort here — they only feed the
      // filter panel's source labels/grouping, so a failure there shouldn't
      // block the job list from loading.
      const [p, data, s, c] = await Promise.allSettled([
        getProfile(),
        getJobs(),
        getSources(),
        getCustomSites(),
      ]);
      if (ignore) return;
      if (p.status === "fulfilled") setProfile(p.value);
      if (data.status === "fulfilled") {
        setJobs(data.value);
      } else {
        setErrorMessage(
          data.reason instanceof ApiError ? data.reason.message : "Couldn't load jobs."
        );
      }
      if (s.status === "fulfilled") setSources(s.value.sources);
      if (c.status === "fulfilled") setCustomSites(c.value.sites);
      setJobsLoading(false);
    }
    bootstrap();
    return () => {
      ignore = true;
    };
  }, []);

  const sourceGroups = useMemo(
    () => buildSourceOptions(jobs, sources, customSites),
    [jobs, sources, customSites]
  );
  const regionOptions = useMemo(() => buildRegionOptions(jobs), [jobs]);
  const filteredJobs = useMemo(() => applyFilters(jobs, filters), [jobs, filters]);

  function startTimer() {
    setElapsed(0);
    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
  }
  function stopTimer() {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  }
  useEffect(() => () => stopTimer(), []);

  async function handleScan() {
    setErrorMessage(null);
    setScanWarnings([]);
    setScanning(true);
    setStatusMessage("Scanning your sources — this can take a minute or two…");
    startTimer();
    try {
      // The registry-driven engine: every enabled source, your own added
      // websites, and any portal you've connected. The old /scan endpoint only
      // ran the handful of v1 aggregators, which is why this button used to sit
      // there for a minute and come back with nothing new.
      const res = await runNow({});
      const ok = res.results.filter((r) => r.status === "ok").length;
      const silent = res.results.filter(
        (r) => r.status === "empty" || r.status === "error",
      ).length;
      const needLogin = res.results.filter((r) => r.status === "needs_login").length;
      setLastRun(res);
      setStatusMessage(
        `Found ${res.jobs_found} job${res.jobs_found === 1 ? "" : "s"} · ` +
          `${res.jobs_new} new · ${ok}/${res.sources_considered} sources returned jobs` +
          (silent ? ` · ${silent} silent` : "") +
          (needLogin ? ` · ${needLogin} need a login` : ""),
      );
      setScanWarnings(res.warnings ?? []);
      await loadJobs();
    } catch (e) {
      setErrorMessage(e instanceof ApiError ? e.message : "The scan failed. Try again.");
      setStatusMessage(null);
    } finally {
      setScanning(false);
      stopTimer();
    }
  }

  async function handleEvaluate() {
    setErrorMessage(null);
    setEvaluating(true);
    setStatusMessage("Evaluating fit against your profile…");
    startTimer();
    try {
      const res = await evaluate({});
      setStatusMessage(`Evaluated ${res.evaluated} job${res.evaluated === 1 ? "" : "s"}.`);
      await loadJobs();
    } catch (e) {
      setErrorMessage(e instanceof ApiError ? e.message : "Evaluation failed. Try again.");
      setStatusMessage(null);
    } finally {
      setEvaluating(false);
      stopTimer();
    }
  }

  const evaluatedCount = jobs.filter((j) => j.evaluation).length;
  const flaggedCount = jobs.filter((j) => j.evaluation?.scam_flag).length;
  const busy = scanning || evaluating;

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-6 py-10">
        <div className="flex flex-col gap-1">
          <h1 className="font-display text-title">Dashboard</h1>
          <p className="text-body text-muted">
            {profile?.target_roles.length
              ? `Scanning for ${profile.target_roles.join(", ")}.`
              : "Scan your sources, then let LaunchPad rank what's worth your time."}
          </p>
        </div>

        {/* Scan controls */}
        <GlassCard as="section" innerClassName="flex flex-col gap-5">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label="Look back (days)"
                type="number"
                min={1}
                max={90}
                value={sinceDays}
                onChange={(e) => setSinceDays(Number(e.target.value) || 1)}
                disabled={busy}
                className="max-w-[10rem]"
              />
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={handleScan} loading={scanning} disabled={busy} size="lg">
                Scan for jobs
              </Button>
              <Button
                onClick={handleEvaluate}
                loading={evaluating}
                disabled={busy || jobs.length === 0}
                variant="secondary"
                size="lg"
              >
                Evaluate all
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-x-8 gap-y-1 border-t border-[color:var(--border)] pt-4 sm:grid-cols-2">
            <Toggle
              checked={fresherOnly}
              onChange={setFresherOnly}
              label="Fresher / entry-level only"
              description="Filter out senior and staff-level roles"
            />
            <Toggle
              checked={crawlCurated}
              onChange={setCrawlCurated}
              label="Include curated niche sources"
              description="Best-effort — slower, occasionally noisy"
            />
          </div>
        </GlassCard>

        {/* Live status — never a frozen UI while long scans/evaluations run */}
        <AnimatePresence>
          {(busy || statusMessage) && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ type: "spring", bounce: 0, duration: 0.3 }}
              className="overflow-hidden"
            >
              <div className="flex items-center gap-3 rounded-xl bg-[color:var(--accent-wash)] px-4 py-3 text-body text-accent">
                {busy && (
                  <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent" />
                )}
                <span className="flex-1">{statusMessage}</span>
                {busy && <span className="tabular-nums text-caption">{elapsed}s</span>}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {errorMessage && (
          <div className="rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger">
            {errorMessage}
          </div>
        )}

        {/* Calm, non-alarming: the scan still succeeded overall — these are
            just the sources that didn't respond this time. */}
        {/* Per-source result of the last scan — the honest answer to
            "which sites did you actually just look at, and what did each give
            me?" Shown right where the scan happened, not buried on another
            page. */}
        {lastRun && (
          <div className="glass overflow-hidden">
            <div className="glass-scrim px-4 py-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-medium text-foreground">
                  Last scan · {lastRun.jobs_found} found, {lastRun.jobs_new} new
                </p>
                <button
                  type="button"
                  onClick={() => setLastRun(null)}
                  className="text-caption text-muted underline underline-offset-2 hover:text-foreground"
                >
                  Hide
                </button>
              </div>
              <ul className="mt-2 grid gap-1 sm:grid-cols-2">
                {[...lastRun.results]
                  .sort((a, b) => b.jobs_found - a.jobs_found)
                  .map((r) => (
                    <li key={r.key} className="flex items-center gap-2 text-caption">
                      <span
                        aria-hidden
                        className={
                          "inline-block h-2 w-2 shrink-0 rounded-full " +
                          (r.status === "ok"
                            ? "bg-success"
                            : r.status === "error"
                              ? "bg-danger"
                              : r.status === "needs_login"
                                ? "bg-accent"
                                : "bg-muted/50")
                        }
                      />
                      <span className="min-w-0 flex-1 truncate text-foreground/80">
                        {r.label}
                      </span>
                      <span className="shrink-0 tabular-nums text-muted">
                        {r.status === "ok"
                          ? `${r.jobs_found}`
                          : r.status === "needs_login"
                            ? "log in"
                            : r.status === "disabled"
                              ? "off"
                              : r.status === "error"
                                ? "error"
                                : "0"}
                      </span>
                    </li>
                  ))}
              </ul>
              <p className="mt-2 text-caption text-muted">
                Portals marked “log in” are skipped until you connect them on the{" "}
                <a className="underline underline-offset-2" href="/connections">
                  Connections
                </a>{" "}
                page.
              </p>
            </div>
          </div>
        )}

        {scanWarnings.length > 0 && (
          <div className="rounded-xl bg-surface-2 px-4 py-3 text-body text-muted">
            <p className="font-medium text-foreground/80">
              Some sources didn&apos;t respond, the rest scanned fine:
            </p>
            <ul className="mt-1 flex flex-col gap-0.5 text-caption">
              {scanWarnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Stats strip */}
        {jobs.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{jobs.length} jobs</Badge>
            <Badge tone="accent">{evaluatedCount} evaluated</Badge>
            {flaggedCount > 0 && <Badge tone="danger">{flaggedCount} flagged</Badge>}
          </div>
        )}

        {/* Filters — client-side over the already-fetched list, so results
            update instantly with no round trip. */}
        {jobs.length > 0 && (
          <FilterPanel
            filters={filters}
            onChange={updateFilters}
            sourceGroups={sourceGroups}
            regionOptions={regionOptions}
            resultCount={filteredJobs.length}
            totalCount={jobs.length}
            onClear={() => setFilters(DEFAULT_FILTERS)}
          />
        )}

        {/* Job list */}
        {jobsLoading ? (
          <div className="flex flex-col gap-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-24 animate-pulse rounded-2xl bg-surface-2" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <EmptyState
            title="No jobs yet"
            description="Run a scan to pull in roles from your configured sources. This app never applies for you — you'll review and open every application yourself."
            action={
              <Button onClick={handleScan} loading={scanning}>
                Scan for jobs
              </Button>
            }
          />
        ) : filteredJobs.length === 0 ? (
          <EmptyState
            title="No jobs match your filters"
            description={
              isDefaultFilters(filters)
                ? "Try adjusting your filters."
                : "Try loosening a filter — a lower minimum score, a wider date range, or fewer selected sources usually finds something."
            }
            action={
              <Button variant="secondary" onClick={() => setFilters(DEFAULT_FILTERS)}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <div className="flex flex-col gap-3">
            {filteredJobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
