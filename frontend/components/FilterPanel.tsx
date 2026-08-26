"use client";

import {
  DATE_POSTED_OPTIONS,
  SORT_OPTIONS,
  isDefaultFilters,
  type DashboardFilters,
  type SourceOption,
} from "@/lib/filters";
import { KIND_LABEL, KIND_ORDER, SCORE_MAX } from "@/lib/utils";
import { GlassCard } from "@/components/GlassCard";
import { Button } from "@/components/Button";

interface FilterPanelProps {
  filters: DashboardFilters;
  onChange: (patch: Partial<DashboardFilters>) => void;
  sourceGroups: Map<string, SourceOption[]>;
  regionOptions: string[];
  resultCount: number;
  totalCount: number;
  onClear: () => void;
}

function toggleInList(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export function FilterPanel({
  filters,
  onChange,
  sourceGroups,
  regionOptions,
  resultCount,
  totalCount,
  onClear,
}: FilterPanelProps) {
  const orderedKinds = [
    ...KIND_ORDER.filter((k) => sourceGroups.has(k)),
    ...Array.from(sourceGroups.keys()).filter((k) => !(KIND_ORDER as string[]).includes(k)),
  ];

  return (
    <GlassCard as="section" innerClassName="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-headline">Filters</h2>
        <div className="flex items-center gap-3">
          <p className="text-caption text-muted tabular-nums">
            Showing {resultCount} of {totalCount} jobs
          </p>
          <Button
            size="sm"
            variant="ghost"
            onClick={onClear}
            disabled={isDefaultFilters(filters)}
          >
            Clear filters
          </Button>
        </div>
      </div>

      {/* Search */}
      <input
        type="search"
        value={filters.search}
        onChange={(e) => onChange({ search: e.target.value })}
        placeholder="Search title, company, or location…"
        aria-label="Search jobs"
        className="w-full rounded-xl border border-[color:var(--border-strong)] bg-surface px-3.5 py-2.5 text-[0.9375rem] text-foreground placeholder:text-muted outline-none transition-[box-shadow,border-color] duration-150 focus:border-accent focus:ring-4 focus:ring-[color:var(--accent-wash)]"
      />

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {/* Min score */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label htmlFor="min-score" className="text-caption text-muted">
              Minimum fit score
            </label>
            <span className="text-caption font-semibold tabular-nums text-foreground">
              {filters.minScore === 0 ? "Any" : `${filters.minScore.toFixed(1)}+`}
            </span>
          </div>
          <input
            id="min-score"
            type="range"
            min={0}
            max={SCORE_MAX}
            step={0.5}
            value={filters.minScore}
            onChange={(e) => onChange({ minScore: Number(e.target.value) })}
            className="range-input"
          />
        </div>

        {/* Region */}
        <div className="flex flex-col gap-2">
          <label htmlFor="region-filter" className="text-caption text-muted">
            Region
          </label>
          <select
            id="region-filter"
            value={filters.region}
            onChange={(e) => onChange({ region: e.target.value })}
            className="rounded-xl border border-[color:var(--border-strong)] bg-surface px-3.5 py-2.5 text-[0.9375rem] text-foreground outline-none focus:border-accent"
          >
            <option value="all">All regions</option>
            {regionOptions.map((r) => (
              <option key={r || "unspecified"} value={r}>
                {r ? r.toUpperCase() : "Unspecified"}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Date posted / first seen */}
      <div className="flex flex-col gap-2">
        <span className="text-caption text-muted">Posted / first seen</span>
        <div className="flex flex-wrap items-center gap-2">
          {DATE_POSTED_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className="chip"
              data-active={filters.datePosted === opt.value}
              onClick={() => onChange({ datePosted: opt.value })}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Sort */}
      <div className="flex flex-col gap-2">
        <span className="text-caption text-muted">Sort by</span>
        <div className="flex flex-wrap items-center gap-2">
          {SORT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className="chip"
              data-active={filters.sort === opt.value}
              onClick={() => onChange({ sort: opt.value })}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Quick toggles */}
      <div className="flex flex-col gap-2 border-t border-[color:var(--border)] pt-4">
        <span className="text-caption text-muted">Quick filters</span>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="chip"
            data-active={filters.entryLevelOnly}
            onClick={() => onChange({ entryLevelOnly: !filters.entryLevelOnly })}
          >
            Entry-level only
          </button>
          <button
            type="button"
            className="chip"
            data-active={filters.sponsorshipOnly}
            onClick={() => onChange({ sponsorshipOnly: !filters.sponsorshipOnly })}
          >
            Sponsorship-friendly only
          </button>
          <button
            type="button"
            className="chip"
            data-active={filters.hideScam}
            onClick={() => onChange({ hideScam: !filters.hideScam })}
          >
            Hide flagged
          </button>
          <button
            type="button"
            className="chip"
            data-active={filters.hideApplied}
            onClick={() => onChange({ hideApplied: !filters.hideApplied })}
          >
            Hide already applied
          </button>
        </div>
      </div>

      {/* Sources, grouped by kind */}
      {sourceGroups.size > 0 && (
        <div className="flex flex-col gap-2 border-t border-[color:var(--border)] pt-4">
          <div className="flex items-center justify-between">
            <span className="text-caption text-muted">
              Sources {filters.sources.length > 0 && `(${filters.sources.length} selected)`}
            </span>
            {filters.sources.length > 0 && (
              <button
                type="button"
                onClick={() => onChange({ sources: [] })}
                className="pressable text-caption font-medium text-accent"
              >
                Reset
              </button>
            )}
          </div>
          <div className="flex max-h-56 flex-col gap-3 overflow-y-auto rounded-xl border border-[color:var(--border)] p-3">
            {orderedKinds.map((kind) => (
              <div key={kind} className="flex flex-col gap-1.5">
                <span className="text-[0.6875rem] font-semibold uppercase tracking-[0.04em] text-muted">
                  {KIND_LABEL[kind] ?? kind}
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {sourceGroups.get(kind)!.map((opt) => (
                    <button
                      key={opt.key}
                      type="button"
                      className="chip"
                      data-active={filters.sources.includes(opt.key)}
                      onClick={() => onChange({ sources: toggleInList(filters.sources, opt.key) })}
                    >
                      {opt.label} · {opt.count}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </GlassCard>
  );
}
