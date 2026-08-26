"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { addCustomSite, ApiError } from "@/lib/api";
import { Field } from "@/components/Field";
import { Button } from "@/components/Button";
import { cn } from "@/lib/utils";

const REGION_OPTIONS: { value: string; label: string }[] = [
  { value: "global", label: "Global" },
  { value: "in", label: "India" },
  { value: "de", label: "Germany" },
];

interface AddWebsiteFormProps {
  onAdded: () => void;
}

// The most-requested feature: "let me give you a link and you scrape it".
// POST /sources/custom rejects anything that isn't a real http(s) URL with a
// readable 400 `detail` — that string is shown verbatim and prominently,
// never truncated, because it's how the user fixes their own input.
export function AddWebsiteForm({ onAdded }: AddWebsiteFormProps) {
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [regions, setRegions] = useState<string[]>(["global"]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function toggleRegion(value: string) {
    setRegions((cur) =>
      cur.includes(value)
        ? cur.length > 1
          ? cur.filter((r) => r !== value)
          : cur // keep at least one selected
        : [...cur, value]
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (!url.trim()) {
      setError("Paste a URL first — the full address, starting with https://");
      return;
    }
    setSubmitting(true);
    try {
      const site = await addCustomSite({
        url: url.trim(),
        label: label.trim() || undefined,
        regions,
      });
      setSuccess(`Added ${site.label}. It'll be included in your next scan.`);
      setUrl("");
      setLabel("");
      setRegions(["global"]);
      onAdded();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Couldn't add that website. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-[2fr_1fr]">
        <Field
          label="Website URL"
          type="url"
          inputMode="url"
          placeholder="https://example.com/careers"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={submitting}
          hint="Point it at a job LIST page — /careers or /jobs — not the homepage."
        />
        <Field
          label="Label (optional)"
          placeholder="Acme Corp"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          disabled={submitting}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-caption text-muted mr-1">Region</span>
        {REGION_OPTIONS.map((r) => (
          <button
            key={r.value}
            type="button"
            className="chip"
            data-active={regions.includes(r.value)}
            disabled={submitting}
            onClick={() => toggleRegion(r.value)}
          >
            {r.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" loading={submitting}>
          Add website
        </Button>
        <p className="text-caption text-muted">
          LaunchPad reads the links on the page you give it. Sites that render listings with
          JavaScript may return nothing.
        </p>
      </div>

      <AnimatePresence mode="wait">
        {error && (
          <motion.div
            key="error"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className={cn(
              "rounded-xl bg-[color:var(--danger-wash)] px-4 py-3 text-body text-danger"
            )}
          >
            {error}
          </motion.div>
        )}
        {success && !error && (
          <motion.div
            key="success"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-xl bg-[color:var(--success-wash)] px-4 py-3 text-body text-success"
          >
            {success}
          </motion.div>
        )}
      </AnimatePresence>
    </form>
  );
}
