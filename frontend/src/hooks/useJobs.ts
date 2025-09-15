import { useCallback, useEffect, useRef, useState } from 'react';
import type { JobDetail, JobItem, JobStatus, InvoiceDisplay } from '@/types/api';
import { createJobs, deleteSession, exportCsv, getJob, listJobs, retryJob } from '@/lib/api';

function toDisplay(detail: JobDetail): InvoiceDisplay | null {
  const r: any = detail.resultJson;
  if (!r) return null;
  try {
    return {
      invoiceNumber: r.invoiceNumber,
      vendorName: r.vendorName,
      invoiceDate:
        typeof r.invoiceDate === 'string'
          ? r.invoiceDate
          : new Date(r.invoiceDate).toISOString().slice(0, 10),
      total: Number(r.total ?? 0),
      currency: typeof r.currency === 'string' ? r.currency.toUpperCase() : undefined,
      jobId: detail.jobId,
    };
  } catch {
    return null;
  }
}

type UiJob = JobItem & { error?: string };

export interface UseJobsReturn {
  jobs: UiJob[];
  results: InvoiceDisplay[];
  onFilesAdded: (files: File[], sessionId: string) => Promise<{ note?: string | null } | void>;
  onRetry: (jobId: string, sessionId: string) => Promise<void>;
  onClearSession: (sessionId: string) => Promise<void>;
  onExport: (sessionId: string) => Promise<void>;
  rehydrate: (sessionId: string) => Promise<void>;
}

export function useJobs(): UseJobsReturn {
  const [jobs, setJobs] = useState<UiJob[]>([]);
  const [results, setResults] = useState<InvoiceDisplay[]>([]);

  const timersRef = useRef<Record<string, number>>({});
  const isMounted = useRef<boolean>(true);
  const seenActiveStageRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    return () => {
      isMounted.current = false;
      // clear timers on unmount
      Object.values(timersRef.current).forEach((id) => window.clearTimeout(id));
      timersRef.current = {};
      seenActiveStageRef.current.clear();
    };
  }, []);

  const schedulePoll = useCallback(
    (jobId: string, sessionId: string, attempt = 0) => {
      // Bursty early polling to avoid missing short-lived statuses (e.g., 'processing')
      const burst = [200, 500, 1000, 1800];
      const fallback = (prev: number) => Math.min(10000, Math.floor(prev * 1.8));
      const base = attempt < burst.length ? burst[attempt] : fallback(burst[burst.length - 1] * Math.pow(1.8, attempt - burst.length));
      const jitter = Math.floor(Math.random() * 200);
      const delay = Math.min(10000, base + jitter);

      const tid = window.setTimeout(async () => {
        if (!isMounted.current) return;
        try {
          const detail = await getJob(jobId, sessionId);
          // Record if we've observed any active stage
          if (detail.status === 'processing' || (detail.status as any) === 'extracting' || (detail.status as any) === 'llm') {
            seenActiveStageRef.current.add(jobId);
          }

          // If backend jumped straight to 'done' and we haven't shown any active stage, simulate a brief 'processing' transition
          if (detail.status === 'done' && !seenActiveStageRef.current.has(jobId)) {
            setJobs((prev: UiJob[]) =>
              prev.map((j: UiJob) =>
                j.jobId === jobId
                  ? {
                      ...j,
                      status: 'processing' as JobStatus,
                      stages: detail.stages || j.stages,
                      sizeBytes: (detail as any).sizeBytes ?? (j as any).sizeBytes,
                      pageCount: (detail as any).pageCount ?? (j as any).pageCount,
                    }
                  : j
              )
            );
            // Show 'Processing' briefly, then finalize to 'done' and add results
            const tid2 = window.setTimeout(() => {
              if (!isMounted.current) return;
              setJobs((prev: UiJob[]) =>
                prev.map((j: UiJob) =>
                  j.jobId === jobId
                    ? {
                        ...j,
                        status: 'done' as JobStatus,
                        stages: detail.stages || j.stages,
                        sizeBytes: (detail as any).sizeBytes ?? (j as any).sizeBytes,
                        pageCount: (detail as any).pageCount ?? (j as any).pageCount,
                      }
                    : j
                )
              );
              const disp = toDisplay(detail);
              if (disp) {
                setResults((prev: InvoiceDisplay[]) => {
                  const idx = prev.findIndex((r: InvoiceDisplay) => r.jobId === disp.jobId);
                  if (idx >= 0) {
                    const next = [...prev];
                    next[idx] = { ...next[idx], ...disp };
                    return next;
                  }
                  return [disp, ...prev];
                });
              }
            }, 500);
            timersRef.current[`${jobId}#bounce`] = tid2 as any;
            return;
          }

          // Normal update path
          setJobs((prev: UiJob[]) =>
            prev.map((j: UiJob) =>
              j.jobId === jobId
                ? {
                    ...j,
                    status: detail.status as JobStatus,
                    stages: detail.stages || j.stages,
                    sizeBytes: (detail as any).sizeBytes ?? (j as any).sizeBytes,
                    pageCount: (detail as any).pageCount ?? (j as any).pageCount,
                    error: (detail as any).error ?? (j as any).error,
                  }
                : j
            )
          );

          if (detail.status === 'done') {
            const disp = toDisplay(detail);
            if (disp) {
              setResults((prev: InvoiceDisplay[]) => {
                const idx = prev.findIndex((r: InvoiceDisplay) => r.jobId === disp.jobId);
                if (idx >= 0) {
                  const next = [...prev];
                  next[idx] = { ...next[idx], ...disp };
                  return next;
                }
                return [disp, ...prev];
              });
            }
          } else if (detail.status === 'failed') {
            // Stop polling on failure
            setJobs((prev: UiJob[]) =>
              prev.map((j: UiJob) => (j.jobId === jobId ? { ...j, status: 'failed' as JobStatus, error: (detail as any).error } : j))
            );
            return;
          } else {
            schedulePoll(jobId, sessionId, attempt + 1);
          }
        } catch (e: any) {
          // Retry with backoff
          schedulePoll(jobId, sessionId, attempt + 1);
        }
      }, delay);

      timersRef.current[jobId] = tid as any;
    },
    []
  );

  const rehydrate = useCallback(async (sessionId: string) => {
    if (!sessionId) return;
    const res = await listJobs(sessionId);
    if (!isMounted.current) return;
    setJobs(res.jobs as UiJob[]);

    // Fetch details for each job, collect completed results, and kick off polling for pending
    await Promise.all(
      res.jobs.map(async (j) => {
        try {
          const d = await getJob(j.jobId, sessionId);
          if (!isMounted.current) return;
          setJobs((prev: UiJob[]) =>
            prev.map((it: UiJob) =>
              it.jobId === j.jobId
                ? {
                    ...it,
                    status: d.status as JobStatus,
                    stages: d.stages || it.stages,
                    sizeBytes: (d as any).sizeBytes ?? (it as any).sizeBytes,
                    pageCount: (d as any).pageCount ?? (it as any).pageCount,
                    error: (d as any).error ?? (it as any).error,
                  }
                : it
            )
          );
          if (d.status === 'done') {
            const disp = toDisplay(d);
            if (disp) {
              setResults((prev: InvoiceDisplay[]) => {
                const idx = prev.findIndex((r: InvoiceDisplay) => r.jobId === disp.jobId);
                if (idx >= 0) {
                  const next = [...prev];
                  next[idx] = { ...next[idx], ...disp };
                  return next;
                }
                return [disp, ...prev];
              });
            }
          } else if (d.status !== 'failed') {
            schedulePoll(j.jobId, sessionId, 0);
          }
        } catch {
          // If getJob fails, schedule polling anyway
          schedulePoll(j.jobId, sessionId, 0);
        }
      })
    );
  }, [schedulePoll]);

  const onFilesAdded = useCallback(async (files: File[], sessionId: string) => {
    if (!sessionId) return;
    const resp = await createJobs(files, sessionId);
    if (!isMounted.current) return;
    setJobs((prev: UiJob[]) => [...(resp.jobs as UiJob[]), ...prev]);
    resp.jobs.forEach((j) => schedulePoll(j.jobId, sessionId, 0));
    return { note: (resp as any).note };
  }, [schedulePoll]);

  const onRetry = useCallback(async (jobId: string, sessionId: string) => {
    if (!sessionId) return;
    await retryJob(jobId, sessionId);
    if (!isMounted.current) return;
    setJobs((prev: UiJob[]) => prev.map((j: UiJob) => (j.jobId === jobId ? { ...j, status: 'queued' as JobStatus } : j)));
    schedulePoll(jobId, sessionId, 0);
  }, [schedulePoll]);

  const onClearSession = useCallback(async (sessionId: string) => {
    if (!sessionId) return;
    try {
      await deleteSession(sessionId);
    } finally {
      if (!isMounted.current) return;
      // clear local state and timers
      Object.values(timersRef.current).forEach((id) => window.clearTimeout(id));
      timersRef.current = {};
      seenActiveStageRef.current.clear();
      setJobs([]);
      setResults([]);
    }
  }, []);

  const onExport = useCallback(async (sessionId: string) => {
    if (!sessionId) return;
    await exportCsv(sessionId);
  }, []);

  return { jobs, results, onFilesAdded, onRetry, onClearSession, onExport, rehydrate };
}
