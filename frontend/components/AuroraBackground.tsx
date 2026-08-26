// Fixed, full-viewport mesh gradient rendered once in app/layout.tsx.
// Pure CSS animation (see .aurora-blob* in globals.css) — no JS motion here,
// so it costs nothing on the main thread and the global
// prefers-reduced-motion guard (globals.css) freezes it automatically.
export function AuroraBackground() {
  return (
    <div className="aurora-backdrop" aria-hidden="true">
      <div className="aurora-blob aurora-blob--1" />
      <div className="aurora-blob aurora-blob--2" />
      <div className="aurora-blob aurora-blob--3" />
      <div className="aurora-blob aurora-blob--4" />
    </div>
  );
}
