"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, getSources, setSourceEnabled, type Source, type SourceKind } from "@/lib/api";
import { NavBar } from "@/components/NavBar";
import { GlassCard } from "@/components/GlassCard";
import { EmptyState } from "@/components/EmptyState";
import { Toggle } from "@/components/Toggle";
import { Badge } from "@/components/Badge";

const KIND_LABEL: Record<string, string> = {
  public: "Public boards",
  ats: "ATS boards",
  portal: "Portals (login required)",
  crawl: "Curated crawls",
};

const KIND_ORDER: SourceKind[] = ["public", "ats", "portal", "crawl"];

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingKeys, setPendingKeys] = useState<Set<string>>(new Set());
  const [toggleError, setToggleError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<string>("all");
  const [regionFilter, setRegionFilter] = useState<string>("all");

  // Ignore-flag guarded so a fast unmount can't set state on a gone component
  // — matches the bootstrap() pattern used elsewhere in this app.
  useEffect(() => {
    let ignore = false;
    async function bootstrap() {
      try {
        const res = await getSources();
        if (ignore) return;
        setSources(res.sources);
        setLoadError(null);
      } catch (e) {
        if (ignore) return;
        setLoadError(e instanceof ApiError ? e.message : "Couldn't load your sources.");
      }
    }
    bootstrap();
    return () => {
      ignore = true;
    };
  }, []);

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
    const prev = sources;
    setSources((cur) => cur?.map((s) => (s.key === source.key ? { ...s, enabled } : s)) ?? cur);
    setPendingKeys((p) => new Set(p).add(source.key));
    try {
      await setSourceEnabled(source.key, enabled);
    } catch (e) {
      setSources(prev ?? null);
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

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-6 py-10">
        <div className="flex flex-col gap-1">
          <h1 className="font-display text-title">Sources</h1>
          <p className="text-body text-muted">
            Everywhere LaunchPad looks for jobs. Turn any of them off if they&apos;re not useful to
            you.
          </p>
        </div>

        {/* Toolbar */}
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

        {loadError && (
          <div className="rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger">
            {loadError}
          </div>
        )}
        {toggleError && (
          <div className="rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger">
            {toggleError}
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
          <section key={kind} className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <h2 className="font-display text-headline">{KIND_LABEL[kind] ?? kind}</h2>
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
                    {source.regions.map((r) => (
                      <Badge key={r} tone="neutral">
                        {r.toUpperCase()}
                      </Badge>
                    ))}
                    {source.requires_login && <Badge tone="accent">Login required</Badge>}
                    {pendingKeys.has(source.key) && (
                      <span className="text-caption text-muted">Saving…</span>
                    )}
                  </div>
                  {source.warning && (
                    <div className="rounded-xl bg-[color:var(--warning-wash)] px-3 py-2 text-caption text-warning">
                      {source.warning}
                    </div>
                  )}
                </GlassCard>
              ))}
            </div>
          </section>
        ))}
      </main>
    </div>
  );
}
