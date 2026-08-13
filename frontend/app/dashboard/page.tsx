"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  ApiError,
  evaluate,
  getJobs,
  getProfile,
  scan,
  type Job,
  type Profile,
} from "@/lib/api";
import { NavBar } from "@/components/NavBar";
import { Button } from "@/components/Button";
import { Toggle } from "@/components/Toggle";
import { Field } from "@/components/Field";
import { JobCard } from "@/components/JobCard";
import { EmptyState } from "@/components/EmptyState";
import { Badge } from "@/components/Badge";

export default function DashboardPage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [sinceDays, setSinceDays] = useState(7);
  const [fresherOnly, setFresherOnly] = useState(true);
  const [crawlCurated, setCrawlCurated] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
      const [p, data] = await Promise.allSettled([getProfile(), getJobs()]);
      if (ignore) return;
      if (p.status === "fulfilled") setProfile(p.value);
      if (data.status === "fulfilled") {
        setJobs(data.value);
      } else {
        setErrorMessage(
          data.reason instanceof ApiError ? data.reason.message : "Couldn't load jobs."
        );
      }
      setJobsLoading(false);
    }
    bootstrap();
    return () => {
      ignore = true;
    };
  }, []);

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
    setScanning(true);
    setStatusMessage("Scanning your sources — this can take a minute or two…");
    startTimer();
    try {
      const res = await scan({ since_days: sinceDays, fresher_only: fresherOnly, crawl_curated: crawlCurated });
      setStatusMessage(`Added ${res.added} new job${res.added === 1 ? "" : "s"} — ${res.total} total.`);
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
          <h1 className="text-title">Dashboard</h1>
          <p className="text-body text-muted">
            {profile?.target_roles.length
              ? `Scanning for ${profile.target_roles.join(", ")}.`
              : "Scan your sources, then let LaunchPad rank what's worth your time."}
          </p>
        </div>

        {/* Scan controls */}
        <section className="flex flex-col gap-5 rounded-2xl border border-[color:var(--border)] bg-surface p-6 shadow-[var(--shadow-card)]">
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
        </section>

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

        {/* Stats strip */}
        {jobs.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{jobs.length} jobs</Badge>
            <Badge tone="accent">{evaluatedCount} evaluated</Badge>
            {flaggedCount > 0 && <Badge tone="danger">{flaggedCount} flagged</Badge>}
          </div>
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
        ) : (
          <div className="flex flex-col gap-3">
            {jobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
