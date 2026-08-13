import type { ReactNode } from "react";
import type { Job, Profile } from "@/lib/api";

interface PrintCVProps {
  profile: Profile;
  job: Job;
  coverLetter?: string | null;
  cvMarkdown?: string | null;
}

// Minimal, dependency-free markdown -> JSX transform. Handles the shapes an
// LLM-tailored one-page CV actually uses: #/##/### headings, "- "/"* " lists,
// **bold** inline spans, and blank-line-separated paragraphs. Not a full
// CommonMark implementation — good enough for print/save-as-PDF output.
function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>;
    }
    return <span key={`${keyPrefix}-${i}`}>{part}</span>;
  });
}

function renderMarkdown(markdown: string): ReactNode[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];

  function flushList(key: string) {
    if (listItems.length === 0) return;
    blocks.push(
      <ul key={key} style={{ fontSize: "10pt", lineHeight: 1.5, paddingLeft: 18, marginBottom: 8 }}>
        {listItems.map((item, i) => (
          <li key={i}>{renderInline(item, `${key}-li-${i}`)}</li>
        ))}
      </ul>
    );
    listItems = [];
  }

  lines.forEach((raw, i) => {
    const line = raw.trim();
    const key = `b-${i}`;

    if (line.startsWith("- ") || line.startsWith("* ")) {
      listItems.push(line.slice(2));
      return;
    }
    flushList(`${key}-list`);

    if (!line) return;

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const size = level === 1 ? "16pt" : level === 2 ? "13pt" : "11pt";
      blocks.push(
        <p key={key} style={{ fontSize: size, fontWeight: 700, marginTop: 10, marginBottom: 4 }}>
          {renderInline(heading[2], key)}
        </p>
      );
      return;
    }

    blocks.push(
      <p key={key} style={{ fontSize: "10pt", lineHeight: 1.5, marginBottom: 6 }}>
        {renderInline(line, key)}
      </p>
    );
  });
  flushList("tail-list");

  return blocks;
}

// Zero-dependency print fallback (apple-design skill: "Craft" — a broken PDF
// path shouldn't strand the user). Prefers the real LLM-tailored CV markdown
// returned by /tailor (cvMarkdown) so what's printed matches what was
// generated; falls back to reconstructing a CV from profile fields only when
// no tailored markdown is available yet (e.g. tailoring hasn't run). Works
// even when the backend's WeasyPrint render is unavailable (GTK missing on
// Windows) — no PDF library involved, just clean HTML the browser's own
// print-to-PDF handles.
export function PrintCV({ profile, job, coverLetter, cvMarkdown }: PrintCVProps) {
  const contactLine = [profile.email, profile.location, profile.work_auth]
    .filter(Boolean)
    .join(" · ");

  if (cvMarkdown && cvMarkdown.trim()) {
    return (
      <div className="print-only" style={{ color: "#000", background: "#fff", padding: "0.5in" }}>
        {renderMarkdown(cvMarkdown)}

        {coverLetter && (
          <>
            <h3 style={{ fontSize: "11pt", fontWeight: 700, marginTop: 16, marginBottom: 4 }}>
              Cover letter
            </h3>
            <p style={{ fontSize: "10pt", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{coverLetter}</p>
          </>
        )}
      </div>
    );
  }

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
