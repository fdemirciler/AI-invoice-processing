import type {
  JobsCreateResponse,
  JobDetail,
  ListJobsResponse,
  Limits,
} from '@/types/api';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api').replace(/\/$/, '');

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
    const msg = await safeError(res);
    throw new Error(`createJobs failed: ${res.status} ${msg}`);
  }
  return res.json();
}

export async function getJob(jobId: string, sessionId: string): Promise<JobDetail> {
  const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}`, {
    headers: withSession({}, sessionId),
    cache: 'no-store',
  });
  if (!res.ok) {
    const msg = await safeError(res);
    throw new Error(`getJob failed: ${res.status} ${msg}`);
  }
  return res.json();
}

export async function listJobs(sessionId: string): Promise<ListJobsResponse> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/jobs`, {
    headers: withSession({}, sessionId),
    cache: 'no-store',
  });
  if (!res.ok) {
    const msg = await safeError(res);
    throw new Error(`listJobs failed: ${res.status} ${msg}`);
  }
  return res.json();
}

export async function retryJob(jobId: string, sessionId: string): Promise<{ jobId: string; status: string }> {
  const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}/retry`, {
    method: 'POST',
    headers: withSession({}, sessionId),
  });
  if (!res.ok) {
    const msg = await safeError(res);
    throw new Error(`retryJob failed: ${res.status} ${msg}`);
  }
  return res.json();
}

export async function exportCsv(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/export.csv`, {
    headers: withSession({}, sessionId),
  });
  if (!res.ok) {
    const msg = await safeError(res);
    throw new Error(`exportCsv failed: ${res.status} ${msg}`);
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
    const msg = await safeError(res);
    throw new Error(`deleteSession failed: ${res.status} ${msg}`);
  }
  return res.json();
}

async function safeError(res: Response): Promise<string> {
  // Clone the response so we don't consume the body stream twice
  const clone = res.clone();
  try {
    const data = await clone.json();
    return typeof (data as any)?.detail === 'string' ? (data as any).detail : JSON.stringify(data);
  } catch {
    try {
      return await res.clone().text();
    } catch {
      return `${res.status} ${res.statusText}`;
    }
  }
}
