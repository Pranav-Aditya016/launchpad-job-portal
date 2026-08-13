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
    try {
      await evaluate({ job_ids: [id] });
      await loadJob();
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
        e instanceof ApiError
          ? e.message
          : "Couldn't generate a PDF. Use Print / Save as PDF below instead."
      );
    } finally {
      setTailoring(false);
    }
  }

  // Assisted apply only: this fetches the real destination URL from the
  // backend, then opens it in a brand-new tab the user drives themselves.
  // Nothing here ever submits a form or posts an application on the user's
  // behalf — see backend/app/api.py::apply for the matching server-side note.
  async function handleApply() {
    if (!job) return;
    setApplying(true);
    try {
      const res = await apply(id);
      window.open(res.url, "_blank", "noopener");
      setApplyOpened(true);
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
          <p className="text-headline">Job not found</p>
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
                {entryLevel && <Badge tone="success">Entry level</Badge>}
                <Badge tone="neutral">{job.source}</Badge>
                {posted && <span className="text-caption text-muted">Posted {posted}</span>}
              </div>
              <h1 className="text-title">{job.title}</h1>
              <p className="text-body text-muted">
                {job.company}
                {job.location && <> · {job.location}</>}
              </p>
            </header>

            {ev?.scam_flag && ev.scam_reason && (
              <div className="rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger">
                <strong>Why this was flagged:</strong> {ev.scam_reason}
              </div>
            )}

            <section className="flex flex-col gap-2 rounded-2xl border border-[color:var(--border)] bg-surface p-6 shadow-[var(--shadow-card)]">
              <h2 className="text-headline">Full description</h2>
              <p className="text-body whitespace-pre-wrap text-foreground/90">
                {job.description || "No description available."}
              </p>
            </section>
          </div>

          {/* Side column — evaluation + actions */}
          <aside className="flex flex-col gap-6">
            <section className="flex flex-col gap-4 rounded-2xl border border-[color:var(--border)] bg-surface p-6 shadow-[var(--shadow-card)]">
              <h2 className="text-headline">Fit evaluation</h2>
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
                </>
              )}
            </section>

            <section className="flex flex-col gap-4 rounded-2xl border border-[color:var(--border)] bg-surface p-6 shadow-[var(--shadow-card)]">
              <h2 className="text-headline">Apply</h2>

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
                {tailorResult && (
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
                {profile && (
                  <Button variant="ghost" size="sm" onClick={() => window.print()}>
                    Print / Save as PDF
                  </Button>
                )}
              </div>
            </section>

            {tailorResult?.cover_letter && (
              <section className="flex flex-col gap-3 rounded-2xl border border-[color:var(--border)] bg-surface p-6 shadow-[var(--shadow-card)]">
                <div className="flex items-center justify-between">
                  <h2 className="text-headline">Cover letter</h2>
                  <CopyButton text={tailorResult.cover_letter} />
                </div>
                <p className="text-body whitespace-pre-wrap text-foreground/90">
                  {tailorResult.cover_letter}
                </p>
              </section>
            )}

            {tailorResult && (
              <section className="flex flex-col gap-3 rounded-2xl border border-[color:var(--border)] bg-surface p-2 shadow-[var(--shadow-card)]">
                <iframe
                  src={outputPdfUrl(id)}
                  title="Tailored CV preview"
                  className="h-[600px] w-full rounded-xl"
                />
              </section>
            )}
          </aside>
        </div>
      </main>

      {profile && <PrintCV profile={profile} job={job} coverLetter={tailorResult?.cover_letter} />}
    </div>
  );
}
