"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "motion/react";
import {
  ApiError,
  deleteCustomSite,
  getCoverage,
  getCustomSites,
  runNow,
  setCustomSiteEnabled,
  setSourceEnabled,
  type CoverageResponse,
  type CustomSite,
  type RunNowResponse,
  type Source,
} from "@/lib/api";
import { NavBar } from "@/components/NavBar";
import { GlassCard } from "@/components/GlassCard";
import { EmptyState } from "@/components/EmptyState";
import { Toggle } from "@/components/Toggle";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { AddWebsiteForm } from "@/components/AddWebsiteForm";
import { CoverageBar, type CoverageSegment } from "@/components/CoverageBar";
import { StatusBadge, type DisplayStatus } from "@/components/StatusBadge";
import { KIND_LABEL, KIND_ORDER, relativeDate } from "@/lib/utils";

// A registered source's status the moment nothing has run it yet, or it's
// switched off — never conflated with "empty" (ran, found nothing) or
// "error" (ran, failed). See components/StatusBadge.tsx.
function deriveSourceStatus(s: Source): DisplayStatus {
  if (!s.enabled) return "disabled";
  return s.last?.status ?? "not_run";
}

function deriveCustomStatus(c: Pick<CustomSite, "enabled" | "last_status">): DisplayStatus {
  if (!c.enabled) return "disabled";
  return (c.last_status || "not_run") as DisplayStatus;
}

const COVERAGE_ORDER: DisplayStatus[] = ["ok", "needs_login", "empty", "error", "not_run", "disabled"];

export default function SourcesPage() {
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [customSites, setCustomSites] = useState<CustomSite[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingKeys, setPendingKeys] = useState<Set<string>>(new Set());
  const [pendingCustomIds, setPendingCustomIds] = useState<Set<string>>(new Set());
  const [toggleError, setToggleError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<string>("all");
  const [regionFilter, setRegionFilter] = useState<string>("all");

  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<RunNowResponse | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // Shared loader for the initial fetch and every post-action refresh (add
  // website, run scan, etc). `shouldApply` lets the mount effect below guard
  // against setting state after a fast unmount, matching the bootstrap()
  // pattern used elsewhere in this app.
  const load = useCallback(async (shouldApply: () => boolean = () => true) => {
    const [covRes, sitesRes] = await Promise.allSettled([getCoverage(), getCustomSites()]);
    if (!shouldApply()) return;
    if (covRes.status === "fulfilled") {
      setCoverage(covRes.value);
      setLoadError(null);
    } else {
      setLoadError(
        covRes.reason instanceof ApiError ? covRes.reason.message : "Couldn't load your sources."
      );
    }
    if (sitesRes.status === "fulfilled") setCustomSites(sitesRes.value.sites);
  }, []);

  useEffect(() => {
    let ignore = false;
    async function bootstrap() {
      await load(() => !ignore);
    }
    bootstrap();
    return () => {
      ignore = true;
    };
  }, [load]);

  const sources = coverage?.sources ?? null;

  // --- transparency summary: every registry source + every custom site ---
  const coverageStats = useMemo(() => {
    if (!sources) return null;
    const rows: DisplayStatus[] = [];
    sources
      .filter((s) => s.key !== "custom:pages") // superseded by the per-site rows below
      .forEach((s) => rows.push(deriveSourceStatus(s)));
    (customSites ?? []).forEach((c) => rows.push(deriveCustomStatus(c)));

    const counts = new Map<DisplayStatus, number>();
    rows.forEach((status) => counts.set(status, (counts.get(status) ?? 0) + 1));
    const segments: CoverageSegment[] = COVERAGE_ORDER.map((status) => ({
      status,
      count: counts.get(status) ?? 0,
    }));
    return {
      segments,
      total: rows.length,
      ok: counts.get("ok") ?? 0,
      silent: (counts.get("empty") ?? 0) + (counts.get("error") ?? 0),
      needsLogin: counts.get("needs_login") ?? 0,
      disabled: counts.get("disabled") ?? 0,
      notRun: counts.get("not_run") ?? 0,
    };
  }, [sources, customSites]);

  const kinds = useMemo(() => {
    const present = new Set((sources ?? []).map((s) => s.kind));
    return KIND_ORDER.filter((k) => present.has(k));
  }, [sources]);

  const regions = useMemo(() => {
    const present = new Set<string>();
    (sources ?? []).forEach((s) => s.regions.forEach((r) => present.add(r)));
    return Array.from(present).sort();
  }, [sources]);

  const filtered = useMemo(() => {
    if (!sources) return [];
    const q = search.trim().toLowerCase();
    return sources.filter((s) => {
      if (kindFilter !== "all" && s.kind !== kindFilter) return false;
      if (regionFilter !== "all" && !s.regions.includes(regionFilter)) return false;
      if (q && !s.label.toLowerCase().includes(q) && !s.key.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [sources, search, kindFilter, regionFilter]);

  const grouped = useMemo(() => {
    const map = new Map<string, Source[]>();
    for (const s of filtered) {
      const list = map.get(s.kind) ?? [];
      list.push(s);
      map.set(s.kind, list);
    }
    return map;
  }, [filtered]);

  async function handleToggle(source: Source, enabled: boolean) {
    setToggleError(null);
    const prev = coverage;
    setCoverage((cur) =>
      cur ? { ...cur, sources: cur.sources.map((s) => (s.key === source.key ? { ...s, enabled } : s)) } : cur
    );
    setPendingKeys((p) => new Set(p).add(source.key));
    try {
      await setSourceEnabled(source.key, enabled);
    } catch (e) {
      setCoverage(prev ?? null);
      setToggleError(
        e instanceof ApiError ? e.message : `Couldn't update ${source.label}. Please try again.`
      );
    } finally {
      setPendingKeys((p) => {
        const next = new Set(p);
        next.delete(source.key);
        return next;
      });
    }
  }

  async function handleCustomToggle(site: CustomSite, enabled: boolean) {
    setToggleError(null);
    const prev = customSites;
    setCustomSites((cur) => cur?.map((s) => (s.id === site.id ? { ...s, enabled } : s)) ?? cur);
    setPendingCustomIds((p) => new Set(p).add(site.id));
    try {
      await setCustomSiteEnabled(site.id, enabled);
    } catch (e) {
      setCustomSites(prev ?? null);
      setToggleError(
        e instanceof ApiError ? e.message : `Couldn't update ${site.label}. Please try again.`
      );
    } finally {
      setPendingCustomIds((p) => {
        const next = new Set(p);
        next.delete(site.id);
        return next;
      });
    }
  }

  async function handleCustomDelete(site: CustomSite) {
    if (!window.confirm(`Remove ${site.label}? This stops LaunchPad from scanning it.`)) return;
    setToggleError(null);
    setPendingCustomIds((p) => new Set(p).add(site.id));
    try {
      await deleteCustomSite(site.id);
      setCustomSites((cur) => cur?.filter((s) => s.id !== site.id) ?? cur);
    } catch (e) {
      setToggleError(
        e instanceof ApiError ? e.message : `Couldn't remove ${site.label}. Please try again.`
      );
    } finally {
      setPendingCustomIds((p) => {
        const next = new Set(p);
        next.delete(site.id);
        return next;
      });
    }
  }

  async function handleRunNow() {
    setRunning(true);
    setRunError(null);
    setRunResult(null);
    try {
      const res = await runNow({});
      setRunResult(res);
      await load();
    } catch (e) {
      setRunError(e instanceof ApiError ? e.message : "The scan failed. Try again.");
    } finally {
      setRunning(false);
    }
  }

  const lastRun = coverage?.last_run;

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 px-6 py-10">
        <div className="flex flex-col gap-1">
          <h1 className="font-display text-title">Sources</h1>
          <p className="text-body text-muted">
            Everywhere LaunchPad looks for jobs — and everywhere it doesn&apos;t, and why.
          </p>
        </div>

        {loadError && (
          <div className="rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger">
            {loadError}
          </div>
        )}

        {/* ---------------- Transparency ---------------- */}
        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="font-display text-headline">Coverage</h2>
              <p className="text-body text-muted">
                {lastRun
                  ? `Last scan ${relativeDate(lastRun.started) ?? lastRun.started} — ${lastRun.trigger}.`
                  : "No scan has run yet."}
              </p>
            </div>
            <Button onClick={handleRunNow} loading={running} size="md">
              Run a scan now
            </Button>
          </div>

          {coverageStats && coverageStats.total > 0 ? (
            <GlassCard innerClassName="flex flex-col gap-5">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                <StatTile label="Total sources" value={coverageStats.total} />
                <StatTile label="Produced jobs" value={coverageStats.ok} tone="var(--success)" />
                <StatTile label="Silent (empty/error)" value={coverageStats.silent} tone="var(--danger)" />
                <StatTile label="Need login" value={coverageStats.needsLogin} tone="var(--accent)" />
                <StatTile label="Disabled" value={coverageStats.disabled} tone="var(--warning)" />
              </div>
              <CoverageBar segments={coverageStats.segments} />
              {coverageStats.needsLogin > 0 && (
                <div className="flex items-center justify-between gap-3 rounded-xl bg-[color:var(--accent-wash)] px-4 py-3 text-body text-accent">
                  <span>
                    {coverageStats.needsLogin} source{coverageStats.needsLogin === 1 ? "" : "s"} need
                    {coverageStats.needsLogin === 1 ? "s" : ""} you signed in before they can run.
                  </span>
                  <Link href="/connections" className="pressable shrink-0 font-medium underline">
                    Connect them →
                  </Link>
                </div>
              )}
            </GlassCard>
          ) : (
            !loadError && (
              <div className="h-32 animate-pulse rounded-[var(--radius-card)] bg-surface-2" />
            )
          )}

          {runError && (
            <div className="rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger">
              {runError}
            </div>
          )}

          <AnimatePresence>
            {runResult && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ type: "spring", bounce: 0, duration: 0.3 }}
                className="overflow-hidden"
              >
                <GlassCard innerClassName="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="font-display text-headline">This scan&apos;s results</h3>
                    <p className="text-caption text-muted">
                      {runResult.sources_considered} considered · {runResult.sources_ok} produced jobs ·{" "}
                      {runResult.jobs_new} new job{runResult.jobs_new === 1 ? "" : "s"}
                    </p>
                  </div>
                  <div className="flex flex-col divide-y divide-[color:var(--border)]">
                    {runResult.results.map((r) => (
                      <div key={r.key} className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-body">{r.label}</span>
                          <StatusBadge status={r.status} />
                          {r.jobs_found > 0 && (
                            <span className="text-caption text-muted">
                              {r.jobs_found} job{r.jobs_found === 1 ? "" : "s"}
                            </span>
                          )}
                          {r.status === "needs_login" && (
                            <Link href="/connections" className="pressable text-caption font-medium text-accent">
                              Connect →
                            </Link>
                          )}
                        </div>
                        {r.detail && <p className="text-caption text-muted">{r.detail}</p>}
                      </div>
                    ))}
                  </div>
                </GlassCard>
              </motion.div>
            )}
          </AnimatePresence>
        </section>

        {/* ---------------- Add a website ---------------- */}
        <section className="flex flex-col gap-4">
          <div>
            <h2 className="font-display text-headline">Add a website</h2>
            <p className="text-body text-muted">
              Give LaunchPad a link — a company careers page, a niche board, anywhere — and it joins
              your scan alongside everything else.
            </p>
          </div>
          <GlassCard innerClassName="flex flex-col gap-4">
            <AddWebsiteForm onAdded={load} />
          </GlassCard>
        </section>

        {/* ---------------- Your websites ---------------- */}
        {customSites && customSites.length > 0 && (
          <section className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <h2 className="font-display text-headline">Your websites</h2>
              <Badge tone="neutral">{customSites.length}</Badge>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {customSites.map((site) => (
                <GlassCard key={site.id} innerClassName="flex flex-col gap-3" hover>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-display text-headline truncate">{site.label}</p>
                      <p className="text-caption text-muted truncate">{site.url}</p>
                    </div>
                    <Toggle
                      checked={site.enabled}
                      onChange={(v) => handleCustomToggle(site, v)}
                      label=""
                      ariaLabel={`${site.enabled ? "Disable" : "Enable"} ${site.label}`}
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={deriveCustomStatus(site)} />
                    {site.last_jobs > 0 && (
                      <Badge tone="neutral">
                        {site.last_jobs} job{site.last_jobs === 1 ? "" : "s"}
                      </Badge>
                    )}
                    {site.regions.map((r) => (
                      <Badge key={r} tone="neutral">
                        {r.toUpperCase()}
                      </Badge>
                    ))}
                    {pendingCustomIds.has(site.id) && (
                      <span className="text-caption text-muted">Saving…</span>
                    )}
                  </div>
                  {site.last_detail && (
                    <p className="text-caption text-muted">{site.last_detail}</p>
                  )}
                  <div className="mt-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={pendingCustomIds.has(site.id)}
                      onClick={() => handleCustomDelete(site)}
                    >
                      Remove
                    </Button>
                  </div>
                </GlassCard>
              ))}
            </div>
          </section>
        )}

        {toggleError && (
          <div className="rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger">
            {toggleError}
          </div>
        )}

        {/* ---------------- Registered sources ---------------- */}
        <section className="flex flex-col gap-4">
          <div>
            <h2 className="font-display text-headline">Registered sources</h2>
            <p className="text-body text-muted">
              Everything LaunchPad ships with, grouped by kind. Turn any of them off if
              they&apos;re not useful to you.
            </p>
          </div>

          <GlassCard innerClassName="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search sources…"
              aria-label="Search sources"
              className="w-full max-w-xs rounded-xl border border-[color:var(--border-strong)] bg-surface px-3.5 py-2 text-[0.9375rem] text-foreground placeholder:text-muted outline-none transition-[box-shadow,border-color] duration-150 focus:border-accent focus:ring-4 focus:ring-[color:var(--accent-wash)]"
            />
            <div className="flex flex-wrap items-center gap-2">
              {regions.length > 0 && (
                <select
                  value={regionFilter}
                  onChange={(e) => setRegionFilter(e.target.value)}
                  aria-label="Filter by region"
                  className="rounded-full border border-[color:var(--border-strong)] bg-surface px-3.5 py-1.5 text-[0.8125rem] font-medium text-foreground outline-none focus:border-accent"
                >
                  <option value="all">All regions</option>
                  {regions.map((r) => (
                    <option key={r} value={r}>
                      {r.toUpperCase()}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </GlassCard>

          {kinds.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="chip"
                data-active={kindFilter === "all"}
                onClick={() => setKindFilter("all")}
              >
                All kinds
              </button>
              {kinds.map((k) => (
                <button
                  key={k}
                  type="button"
                  className="chip"
                  data-active={kindFilter === k}
                  onClick={() => setKindFilter(k)}
                >
                  {KIND_LABEL[k] ?? k}
                </button>
              ))}
            </div>
          )}

          {sources === null && !loadError && (
            <div className="flex flex-col gap-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-20 animate-pulse rounded-[var(--radius-card)] bg-surface-2" />
              ))}
            </div>
          )}

          {sources && sources.length === 0 && (
            <EmptyState
              title="No sources registered yet"
              description="Job sources are still being wired up behind the scenes. Once they're registered, they'll show up here, grouped by kind, with a switch to turn each one on or off."
            />
          )}

          {sources && sources.length > 0 && filtered.length === 0 && (
            <EmptyState
              title="No sources match your filters"
              description="Try a different search term, kind, or region."
            />
          )}

          {KIND_ORDER.filter((k) => grouped.has(k)).map((kind) => (
            <div key={kind} className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <h3 className="font-display text-headline">{KIND_LABEL[kind] ?? kind}</h3>
                <Badge tone="neutral">{grouped.get(kind)!.length}</Badge>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {grouped.get(kind)!.map((source) => (
                  <GlassCard key={source.key} innerClassName="flex flex-col gap-3" hover>
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-display text-headline min-w-0 truncate">{source.label}</p>
                      <Toggle
                        checked={source.enabled}
                        onChange={(v) => handleToggle(source, v)}
                        label=""
                        ariaLabel={`${source.enabled ? "Disable" : "Enable"} ${source.label}`}
                      />
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <StatusBadge status={deriveSourceStatus(source)} />
                      {source.last && source.last.jobs_found > 0 && (
                        <Badge tone="neutral">
                          {source.last.jobs_found} job{source.last.jobs_found === 1 ? "" : "s"}
                        </Badge>
                      )}
                      {source.regions.map((r) => (
                        <Badge key={r} tone="neutral">
                          {r.toUpperCase()}
                        </Badge>
                      ))}
                      {pendingKeys.has(source.key) && (
                        <span className="text-caption text-muted">Saving…</span>
                      )}
                    </div>
                    {source.requires_login && (
                      <Link
                        href="/connections"
                        className="pressable w-fit text-caption font-medium text-accent"
                      >
                        Manage connection →
                      </Link>
                    )}
                    {source.last?.detail && (
                      <p className="text-caption text-muted">{source.last.detail}</p>
                    )}
                    {source.warning && (
                      <div className="rounded-xl bg-[color:var(--warning-wash)] px-3 py-2 text-caption text-warning">
                        {source.warning}
                      </div>
                    )}
                  </GlassCard>
                ))}
              </div>
            </div>
          ))}
        </section>
      </main>
    </div>
  );
}

function StatTile({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="glass p-1">
      <div className="glass-scrim flex flex-col gap-0.5 px-3.5 py-3">
        <span className="text-caption text-muted">{label}</span>
        <span className="font-display text-title tabular-nums" style={tone ? { color: tone } : undefined}>
          {value}
        </span>
      </div>
    </div>
  );
}
