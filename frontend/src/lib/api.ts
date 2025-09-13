import type {
  JobsCreateResponse,
  JobDetail,
  ListJobsResponse,
  Limits,
} from '@/types/api';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api').replace(/\/$/, '');

export type RateLimitInfo = {
  retryAfterSec: number;
  resetEpoch?: number;
  detail?: string;
};

export class HttpError extends Error {
  status: number;
  detail?: string;
  rateLimit?: RateLimitInfo;
  constructor(message: string, status: number, detail?: string, rateLimit?: RateLimitInfo) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
    this.detail = detail;
    this.rateLimit = rateLimit;
  }
}

async function parseRateLimit(res: Response): Promise<HttpError> {
  const retryAfter = parseInt(res.headers.get('Retry-After') || '0', 10);
  const resetEpoch = parseInt(res.headers.get('X-RateLimit-Reset') || '0', 10);
  let detail = '';
  try {
    const data = await res.json();
    detail = typeof (data as any)?.detail === 'string' ? (data as any).detail : JSON.stringify(data);
  } catch {
    detail = await res.text();
  }
  const rl: RateLimitInfo = { retryAfterSec: Math.max(0, retryAfter || 0), resetEpoch: resetEpoch || undefined, detail };
  return new HttpError(`rate limited: ${detail || res.statusText}`, 429, detail, rl);
}

function withSession(headers: HeadersInit, sessionId: string): HeadersInit {
  return {
    ...headers,
    'X-Session-Id': sessionId,
  };
}

export async function getConfig(): Promise<Limits> {
  const res = await fetch(`${API_BASE}/config`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`getConfig failed: ${res.status}`);
  return res.json();
}

export async function createJobs(files: File[], sessionId: string): Promise<JobsCreateResponse> {
  const fd = new FormData();
  for (const f of files) fd.append('files', f, f.name);
  const res = await fetch(`${API_BASE}/jobs`, {
    method: 'POST',
    headers: withSession({}, sessionId),
    body: fd,
  });
  if (!res.ok) {
    if (res.status === 429) throw await parseRateLimit(res);
    const msg = await safeError(res);
    throw new HttpError(`createJobs failed: ${res.status} ${msg}`, res.status, msg);
  }
  return res.json();
}

export async function getJob(jobId: string, sessionId: string): Promise<JobDetail> {
  const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}`, {
    headers: withSession({}, sessionId),
    cache: 'no-store',
  });
  if (!res.ok) {
    if (res.status === 429) throw await parseRateLimit(res);
    const msg = await safeError(res);
    throw new HttpError(`getJob failed: ${res.status} ${msg}`, res.status, msg);
  }
  return res.json();
}

export async function listJobs(sessionId: string): Promise<ListJobsResponse> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/jobs`, {
    headers: withSession({}, sessionId),
    cache: 'no-store',
  });
  if (!res.ok) {
    if (res.status === 429) throw await parseRateLimit(res);
    const msg = await safeError(res);
    throw new HttpError(`listJobs failed: ${res.status} ${msg}`, res.status, msg);
  }
  return res.json();
}

export async function retryJob(jobId: string, sessionId: string): Promise<{ jobId: string; status: string }> {
  const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}/retry`, {
    method: 'POST',
    headers: withSession({}, sessionId),
  });
  if (!res.ok) {
    if (res.status === 429) throw await parseRateLimit(res);
    const msg = await safeError(res);
    throw new HttpError(`retryJob failed: ${res.status} ${msg}`, res.status, msg);
  }
  return res.json();
}

export async function exportCsv(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/export.csv`, {
    headers: withSession({}, sessionId),
  });
  if (!res.ok) {
    if (res.status === 429) throw await parseRateLimit(res);
    const msg = await safeError(res);
    throw new HttpError(`exportCsv failed: ${res.status} ${msg}`, res.status, msg);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `export-${sessionId}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function deleteSession(sessionId: string): Promise<{ sessionId: string; deleted: number }> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: withSession({}, sessionId),
  });
  if (!res.ok) {
    if (res.status === 429) throw await parseRateLimit(res);
    const msg = await safeError(res);
    throw new HttpError(`deleteSession failed: ${res.status} ${msg}`, res.status, msg);
  }
  return res.json();
}

async function safeError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return typeof data?.detail === 'string' ? data.detail : JSON.stringify(data);
  } catch {
    return await res.text();
  }
}
