"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "motion/react";
import {
  ApiError,
  apply,
  evaluate,
  getJobs,
  getProfile,
  outputPdfUrl,
  tailor,
  type Job,
  type Profile,
  type TailorResponse,
} from "@/lib/api";
import { NavBar } from "@/components/NavBar";
import { Button } from "@/components/Button";
import { Badge } from "@/components/Badge";
import { ScoreDial } from "@/components/ScoreDial";
import { CopyButton } from "@/components/CopyButton";
import { PrintCV } from "@/components/PrintCV";
import { GlassCard } from "@/components/GlassCard";
import { isEntryLevel, relativeDate } from "@/lib/utils";

export default function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [job, setJob] = useState<Job | null | undefined>(undefined); // undefined = loading
  const [profile, setProfile] = useState<Profile | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [tailoring, setTailoring] = useState(false);
  const [tailorResult, setTailorResult] = useState<TailorResponse | null>(null);
  const [tailorError, setTailorError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [applyOpened, setApplyOpened] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [evaluateError, setEvaluateError] = useState<string | null>(null);

  async function loadJob() {
    const jobs = await getJobs();
    setJob(jobs.find((j) => j.id === id) ?? null);
  }

  useEffect(() => {
    let ignore = false;
    async function bootstrap() {
      const [jobs, p] = await Promise.all([
        getJobs(),
        getProfile().catch(() => null),
      ]);
      if (ignore) return;
      setJob(jobs.find((j) => j.id === id) ?? null);
      setProfile(p);
    }
    bootstrap();
    return () => {
      ignore = true;
    };
  }, [id]);

  async function handleEvaluate() {
    setEvaluating(true);
    setEvaluateError(null);
    try {
      await evaluate({ job_ids: [id] });
      await loadJob();
    } catch (e) {
      setEvaluateError(
        e instanceof ApiError ? e.message : "Couldn't evaluate this job. Please try again."
      );
    } finally {
      setEvaluating(false);
    }
  }

  async function handleTailor() {
    setTailoring(true);
    setTailorError(null);
    try {
      const res = await tailor(id);
      setTailorResult(res);
    } catch (e) {
      setTailorError(
        e instanceof ApiError ? e.message : "Couldn't tailor this CV. Please try again."
      );
    } finally {
      setTailoring(false);
    }
  }

  // Only http(s) URLs are safe to hand to window.open — job URLs originate
  // from third-party feeds and markdown-link extraction (crawl4ai), so a
  // malformed or malicious `javascript:`/`data:` URL is not impossible.
  const SAFE_URL = /^https?:\/\//i;

  // Assisted apply only: this fetches the real destination URL from the
  // backend, then opens it in a brand-new tab the user drives themselves.
  // Nothing here ever submits a form or posts an application on the user's
  // behalf — see backend/app/api.py::apply for the matching server-side note.
  async function handleApply() {
    if (!job) return;
    setApplying(true);
    setApplyError(null);
    try {
      const res = await apply(id);
      if (!SAFE_URL.test(res.url)) {
        setApplyError("This job's apply link looks unsafe, so it wasn't opened.");
        return;
      }
      window.open(res.url, "_blank", "noopener");
      setApplyOpened(true);
    } catch (e) {
      setApplyError(
        e instanceof ApiError ? e.message : "Couldn't open the apply page. Please try again."
      );
    } finally {
      setApplying(false);
    }
  }

  if (job === undefined) {
    return (
      <div className="flex min-h-screen flex-col">
        <NavBar />
        <main className="mx-auto flex w-full max-w-4xl flex-1 items-center justify-center px-6 text-body text-muted">
          Loading…
        </main>
      </div>
    );
  }

  if (job === null) {
    return (
      <div className="flex min-h-screen flex-col">
        <NavBar />
        <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
          <p className="font-display text-headline">Job not found</p>
          <p className="text-body text-muted">It may have been removed from the local store.</p>
          <Link href="/dashboard" className="pressable text-accent font-medium">
            Back to dashboard
          </Link>
        </main>
      </div>
    );
  }

  const ev = job.evaluation;
  const entryLevel = isEntryLevel(job.title);
  const posted = relativeDate(job.posted);

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="no-print mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
        <Link href="/dashboard" className="pressable text-[0.875rem] font-medium text-muted w-fit">
          ← Back to dashboard
        </Link>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Main column */}
          <div className="flex flex-col gap-6 lg:col-span-2">
            <header className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2">
                {ev?.scam_flag && <Badge tone="danger">Possible scam</Badge>}
                {ev?.no_sponsorship && <Badge tone="warning">No sponsorship</Badge>}
                {job.sponsorship_ok === true && (
                  <Badge tone="neutral">Sponsorship likely OK</Badge>
                )}
                {entryLevel && <Badge tone="success">Entry level</Badge>}
                {job.applied && <Badge tone="accent">Applied</Badge>}
                <Badge tone="neutral">{job.source}</Badge>
                {job.region && <Badge tone="neutral">{job.region.toUpperCase()}</Badge>}
                {posted && <span className="text-caption text-muted">Posted {posted}</span>}
              </div>
              <h1 className="font-display text-title">{job.title}</h1>
              <p className="text-body text-muted">
                {job.company}
                {job.location && <> · {job.location}</>}
              </p>
              {/* Provenance: exactly which source this came from, and a
                  direct link to the real posting — separate from "Open apply
                  page" below, which is the assisted-apply flow. */}
              {SAFE_URL.test(job.url) && (
                <a
                  href={job.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="pressable w-fit text-[0.875rem] font-medium text-accent hover:underline"
                >
                  View original posting on {job.source} ↗
                </a>
              )}
            </header>

            {ev?.scam_flag && ev.scam_reason && (
              <div className="rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger">
                <strong>Why this was flagged:</strong> {ev.scam_reason}
              </div>
            )}

            <GlassCard as="section" innerClassName="flex flex-col gap-2">
              <h2 className="font-display text-headline">Full description</h2>
              <p className="text-body whitespace-pre-wrap text-foreground/90">
                {job.description || "No description available."}
              </p>
            </GlassCard>
          </div>

          {/* Side column — evaluation + actions */}
          <aside className="flex flex-col gap-6">
            <GlassCard as="section" innerClassName="flex flex-col gap-4">
              <h2 className="font-display text-headline">Fit evaluation</h2>
              {ev ? (
                <>
                  <div className="flex items-center gap-3">
                    <ScoreDial score={ev.score} size={64} strokeWidth={6} />
                    <p className="text-body text-muted">{ev.summary}</p>
                  </div>

                  <div>
                    <p className="text-caption text-muted mb-1">CV match</p>
                    <p className="text-body">{ev.cv_match}</p>
                  </div>

                  {ev.strengths.length > 0 && (
                    <div>
                      <p className="text-caption text-muted mb-1">Strengths</p>
                      <ul className="flex flex-col gap-1">
                        {ev.strengths.map((s, i) => (
                          <li key={i} className="text-body flex gap-2">
                            <span className="text-success">+</span>
                            {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {ev.gaps.length > 0 && (
                    <div>
                      <p className="text-caption text-muted mb-1">Gaps</p>
                      <ul className="flex flex-col gap-1">
                        {ev.gaps.map((g, i) => (
                          <li key={i} className="text-body flex gap-2">
                            <span className="text-warning">−</span>
                            {g}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <p className="text-body text-muted">Not evaluated yet.</p>
                  <Button onClick={handleEvaluate} loading={evaluating} size="sm">
                    Evaluate this job
                  </Button>
                  {evaluateError && (
                    <p className="text-caption text-danger">{evaluateError}</p>
                  )}
                </>
              )}
            </GlassCard>

            <GlassCard as="section" innerClassName="flex flex-col gap-4">
              <h2 className="font-display text-headline">Apply</h2>

              <Button onClick={handleApply} loading={applying} size="lg">
                Open apply page
              </Button>
              <p className="text-caption text-muted">
                This opens the real application page on the employer&apos;s site in a new tab. You
                review it and submit it yourself — LaunchPad never applies on your behalf.
              </p>
              <AnimatePresence>
                {applyOpened && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="text-caption text-success"
                  >
                    Apply page opened in a new tab.
                  </motion.p>
                )}
              </AnimatePresence>
              {applyError && <p className="text-caption text-danger">{applyError}</p>}

              <div className="border-t border-[color:var(--border)] pt-4 flex flex-col gap-3">
                <Button
                  onClick={handleTailor}
                  loading={tailoring}
                  variant="secondary"
                  disabled={!ev}
                >
                  Tailor CV
                </Button>
                {!ev && <p className="text-caption text-muted">Evaluate this job first.</p>}
                {tailorError && (
                  <p className="text-caption text-danger">{tailorError}</p>
                )}
                {tailorResult?.pdf_available && (
                  <div className="flex flex-col gap-2">
                    <a
                      href={outputPdfUrl(id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="pressable text-[0.875rem] font-medium text-accent"
                    >
                      Open tailored CV (PDF) ↗
                    </a>
                  </div>
                )}
                {tailorResult && !tailorResult.pdf_available && (
                  <p className="text-caption text-muted">
                    Your tailored CV is ready, but server-side PDF rendering isn&apos;t available on
                    this machine. Use &ldquo;Print / Save as PDF&rdquo; below to save it — installing
                    the GTK runtime enables server-side PDFs too.
                  </p>
                )}
                {profile && (
                  <Button variant="ghost" size="sm" onClick={() => window.print()}>
                    Print / Save as PDF
                  </Button>
                )}
              </div>
            </GlassCard>

            {tailorResult?.cover_letter && (
              <GlassCard as="section" innerClassName="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <h2 className="font-display text-headline">Cover letter</h2>
                  <CopyButton text={tailorResult.cover_letter} />
                </div>
                <p className="text-body whitespace-pre-wrap text-foreground/90">
                  {tailorResult.cover_letter}
                </p>
              </GlassCard>
            )}

            {tailorResult?.pdf_available && (
              <GlassCard as="section" innerClassName="p-2" noPadding>
                <iframe
                  src={outputPdfUrl(id)}
                  title="Tailored CV preview"
                  className="h-[600px] w-full rounded-xl"
                />
              </GlassCard>
            )}
          </aside>
        </div>
      </main>

      {profile && (
        <PrintCV
          profile={profile}
          job={job}
          coverLetter={tailorResult?.cover_letter}
          cvMarkdown={tailorResult?.cv_markdown}
        />
      )}
    </div>
  );
}
