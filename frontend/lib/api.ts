// Typed client for the LaunchPad backend (see backend/app/api.py).
// Every function here maps 1:1 to a single REST endpoint — no hidden
// batching, no client-side mutation of server state beyond what the
// endpoint itself performs.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Profile {
  name: string;
  email: string;
  location: string;
  work_auth: string;
  target_roles: string[];
  skills: string[];
  proof_points: string[];
  resume_text: string;
}

export interface Evaluation {
  job_id: string;
  score: number;
  summary: string;
  cv_match: string;
  scam_flag: boolean;
  scam_reason: string;
  no_sponsorship: boolean;
  strengths: string[];
  gaps: string[];
}

export interface Job {
  id: string;
  source: string;
  company: string;
  title: string;
  location: string;
  url: string;
  description: string;
  posted: string | null;
  evaluation: Evaluation | null;
  // Visa-sponsorship SIGNAL (see backend/app/sources/visa.py) — a soft
  // ranking input, not a hard filter. Optional because older cached job
  // records (or a backend that hasn't been redeployed yet) may not have it.
  sponsorship_ok?: boolean;
  // Whether the user has already used /apply/{id} for this job.
  applied?: boolean;
}

export interface CrawlUrl {
  url: string;
  company: string;
}

export interface ScanRequest {
  ats?: string[];
  since_days?: number;
  crawl_urls?: CrawlUrl[];
  aggregators?: string[];
  fresher_only?: boolean;
  crawl_curated?: boolean;
}

export interface ScanResponse {
  added: number;
  total: number;
  warnings?: string[];
}

export interface EvaluateRequest {
  job_ids?: string[];
}

export interface EvaluateResponse {
  evaluated: number;
  failed?: number;
  warnings?: string[];
}

export interface TailorResponse {
  pdf_url: string | null;
  cover_letter: string;
  cv_markdown: string;
  pdf_available: boolean;
}

export interface ApplyResponse {
  url: string;
}

// See backend/app/routes/connections.py. GET is real; the three action
// routes return HTTP 501 (naming the owning track) until Track C's session
// vault lands — callers should treat 501 as "not live yet", not an error.
export type ConnectionStatus = "disconnected" | "connected" | "expired" | "checking" | "blocked";

export interface Connection {
  portal: string;
  label: string;
  login_url: string;
  status: ConnectionStatus;
  last_verified: string | null;
  note: string;
  warning: string;
}

export interface ConnectionActionResult {
  ok: boolean;
  notYetImplemented: boolean;
  message?: string;
}

// See backend/app/routes/sources.py.
export type SourceKind = "public" | "ats" | "portal" | "crawl";

export interface Source {
  key: string;
  label: string;
  kind: SourceKind;
  regions: string[];
  requires_login: boolean;
  enabled: boolean;
  warning: string;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(
      0,
      "Can't reach the LaunchPad backend. Is it running on " + API_URL + "?"
    );
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // body wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function uploadResume(file: File): Promise<Profile> {
  const form = new FormData();
  form.append("file", file);
  return request<Profile>("/resume", { method: "POST", body: form });
}

export function getProfile(): Promise<Profile | null> {
  return request<Profile | null>("/profile");
}

export function scan(body: ScanRequest = {}): Promise<ScanResponse> {
  return request<ScanResponse>("/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getJobs(): Promise<Job[]> {
  return request<Job[]>("/jobs");
}

export function evaluate(body: EvaluateRequest = {}): Promise<EvaluateResponse> {
  return request<EvaluateResponse>("/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function tailor(jobId: string): Promise<TailorResponse> {
  return request<TailorResponse>(`/tailor/${jobId}`, { method: "POST" });
}

export function apply(jobId: string): Promise<ApplyResponse> {
  return request<ApplyResponse>(`/apply/${jobId}`, { method: "POST" });
}

export function outputPdfUrl(jobId: string): string {
  return `${API_URL}/output/${jobId}.pdf`;
}

export function getConnections(): Promise<{ connections: Connection[] }> {
  return request<{ connections: Connection[] }>("/connections");
}

// The three action endpoints are wrapped so a 501 ("not yet implemented by
// the owning track") resolves normally instead of throwing — callers show a
// friendly "coming online shortly" state rather than an error explosion.
async function connectionAction(path: string, init: RequestInit): Promise<ConnectionActionResult> {
  try {
    await request<unknown>(path, init);
    return { ok: true, notYetImplemented: false };
  } catch (e) {
    if (e instanceof ApiError && e.status === 501) {
      return { ok: false, notYetImplemented: true, message: e.message };
    }
    throw e;
  }
}

export function startConnectionLogin(portal: string): Promise<ConnectionActionResult> {
  return connectionAction(`/connections/${portal}/login`, { method: "POST" });
}

export function verifyConnection(portal: string): Promise<ConnectionActionResult> {
  return connectionAction(`/connections/${portal}/verify`, { method: "POST" });
}

export function disconnectConnection(portal: string): Promise<ConnectionActionResult> {
  return connectionAction(`/connections/${portal}`, { method: "DELETE" });
}

export function getSources(): Promise<{ sources: Source[] }> {
  return request<{ sources: Source[] }>("/sources");
}

export function setSourceEnabled(key: string, enabled: boolean): Promise<{ key: string; enabled: boolean }> {
  return request<{ key: string; enabled: boolean }>(`/sources/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

export { ApiError, API_URL };
