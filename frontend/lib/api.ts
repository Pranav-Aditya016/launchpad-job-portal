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
}

export interface EvaluateRequest {
  job_ids?: string[];
}

export interface EvaluateResponse {
  evaluated: number;
}

export interface TailorResponse {
  pdf_url: string;
  cover_letter: string;
}

export interface ApplyResponse {
  url: string;
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

export { ApiError, API_URL };
