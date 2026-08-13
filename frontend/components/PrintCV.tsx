import type { Job, Profile } from "@/lib/api";

interface PrintCVProps {
  profile: Profile;
  job: Job;
  coverLetter?: string | null;
}

// Zero-dependency print fallback (apple-design skill: "Craft" — a broken PDF
// path shouldn't strand the user). This renders straight from data the app
// already has in memory (profile + job + an already-fetched cover letter),
// so it works even when the backend's WeasyPrint render is unavailable
// (GTK missing on Windows) — no PDF library involved, just clean HTML the
// browser's own print-to-PDF handles.
export function PrintCV({ profile, job, coverLetter }: PrintCVProps) {
  const contactLine = [profile.email, profile.location, profile.work_auth]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="print-only" style={{ color: "#000", background: "#fff", padding: "0.5in" }}>
      <h1 style={{ fontSize: "22pt", fontWeight: 700, marginBottom: 2 }}>
        {profile.name || "Candidate"}
      </h1>
      {contactLine && <p style={{ fontSize: "10pt", marginBottom: 16 }}>{contactLine}</p>}

      <h2 style={{ fontSize: "13pt", fontWeight: 700, marginTop: 12, marginBottom: 4 }}>
        Applying for {job.title} at {job.company}
      </h2>

      {profile.target_roles.length > 0 && (
        <p style={{ fontSize: "10pt", marginBottom: 10 }}>
          <strong>Target roles:</strong> {profile.target_roles.join(", ")}
        </p>
      )}

      {profile.skills.length > 0 && (
        <>
          <h3 style={{ fontSize: "11pt", fontWeight: 700, marginTop: 10, marginBottom: 4 }}>Skills</h3>
          <p style={{ fontSize: "10pt", lineHeight: 1.5 }}>{profile.skills.join(", ")}</p>
        </>
      )}

      {profile.proof_points.length > 0 && (
        <>
          <h3 style={{ fontSize: "11pt", fontWeight: 700, marginTop: 10, marginBottom: 4 }}>
            Highlights
          </h3>
          <ul style={{ fontSize: "10pt", lineHeight: 1.5, paddingLeft: 18 }}>
            {profile.proof_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </>
      )}

      {coverLetter && (
        <>
          <h3 style={{ fontSize: "11pt", fontWeight: 700, marginTop: 16, marginBottom: 4 }}>
            Cover letter
          </h3>
          <p style={{ fontSize: "10pt", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{coverLetter}</p>
        </>
      )}

      {!coverLetter && profile.resume_text && (
        <>
          <h3 style={{ fontSize: "11pt", fontWeight: 700, marginTop: 16, marginBottom: 4 }}>
            Resume
          </h3>
          <p style={{ fontSize: "9pt", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
            {profile.resume_text}
          </p>
        </>
      )}
    </div>
  );
}
