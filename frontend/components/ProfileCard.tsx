"use client";

import type { Profile } from "@/lib/api";
import { Field, TagListField } from "@/components/Field";
import { GlassCard } from "@/components/GlassCard";

interface ProfileCardProps {
  profile: Profile;
  onChange: (profile: Profile) => void;
}

// Editable review of the parsed resume. There is no PUT /profile on the
// backend, so edits here are a local review pass, not a server write — the
// caption makes that explicit rather than implying a save that doesn't happen.
export function ProfileCard({ profile, onChange }: ProfileCardProps) {
  function set<K extends keyof Profile>(key: K, value: Profile[K]) {
    onChange({ ...profile, [key]: value });
  }

  return (
    <GlassCard innerClassName="flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Name" value={profile.name} onChange={(e) => set("name", e.target.value)} />
        <Field label="Email" value={profile.email} onChange={(e) => set("email", e.target.value)} />
        <Field label="Location" value={profile.location} onChange={(e) => set("location", e.target.value)} />
        <Field
          label="Work authorization"
          value={profile.work_auth}
          onChange={(e) => set("work_auth", e.target.value)}
          placeholder="e.g. U.S. citizen, needs H-1B sponsorship"
        />
      </div>

      <TagListField
        label="Target roles"
        values={profile.target_roles}
        onChange={(v) => set("target_roles", v)}
        placeholder="One per line — e.g. Software Engineer"
        hint="One per line. Used to shape the job scan."
      />
      <TagListField
        label="Skills"
        values={profile.skills}
        onChange={(v) => set("skills", v)}
        placeholder="One per line"
      />
      <TagListField
        label="Proof points"
        values={profile.proof_points}
        onChange={(v) => set("proof_points", v)}
        placeholder="One per line — concrete achievements"
        hint="Used to tailor your CV and cover letters."
      />

      <p className="text-caption text-muted border-t border-[color:var(--border)] pt-4">
        These edits are a review pass in your browser only — scans and evaluations run against the
        resume file already on record. To change what the engine reads, upload a new resume.
      </p>
    </GlassCard>
  );
}
