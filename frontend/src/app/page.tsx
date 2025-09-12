"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { ResultsTable } from '@/components/invoice-insights/results-table';
import { Sparkles, Moon, Sun, RefreshCcw, Github } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { SmartHub } from '@/components/invoice-insights/smart-hub';
import { resetSessionId } from '@/lib/session';
import { getConfig, listJobs, createJobs, getJob, retryJob, deleteSession, exportCsv } from '@/lib/api';
import type { Limits, JobItem, JobDetail, InvoiceDisplay, JobStatus } from '@/types/api';


// --- Helpers ---
function toDisplay(detail: JobDetail): InvoiceDisplay | null {
  const r: any = detail.resultJson;
  if (!r) return null;
  try {
    return {
      invoiceNumber: r.invoiceNumber,
      vendorName: r.vendorName,
      invoiceDate: typeof r.invoiceDate === 'string' ? r.invoiceDate : new Date(r.invoiceDate).toISOString().slice(0, 10),
      total: Number(r.total ?? 0),
      currency: typeof r.currency === 'string' ? r.currency.toUpperCase() : undefined,
      jobId: detail.jobId,
    };
  } catch {
    return null;
  }
}


// --- Main Component ---
type UiJob = JobItem & { error?: string };

export default function Home() {
  const [sessionId, setSessionId] = useState<string>('');
  const [limits, setLimits] = useState<Limits | null>(null);
  const [jobs, setJobs] = useState<UiJob[]>([]);
  const [results, setResults] = useState<InvoiceDisplay[]>([]);
  const [theme, setTheme] = useState('dark');
  const { toast } = useToast();
  const isMounted = useRef(true);
  // Track whether we've seen an active stage for a job, to avoid skipping straight from queued -> done in the UI
  const seenActiveStageRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    setTheme(savedTheme);
    // On browser refresh, create a brand new session
    const sid = resetSessionId();
    setSessionId(sid);
    return () => {
      isMounted.current = false;
    };
  }, []);

  useEffect(() => {
    document.documentElement.className = theme;
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme((prev: string) => (prev === 'dark' ? 'light' : 'dark'));

  const schedulePoll = useCallback(
    (jobId: string, attempt = 0) => {
      // Bursty early polling to avoid missing short-lived statuses (e.g., 'processing')
      const burst = [200, 500, 1000, 1800];
      const fallback = (prev: number) => Math.min(10000, Math.floor(prev * 1.8));
      const base = attempt < burst.length ? burst[attempt] : fallback(burst[burst.length - 1] * Math.pow(1.8, attempt - burst.length));
      const jitter = Math.floor(Math.random() * 200);
      const delay = Math.min(10000, base + jitter);
      window.setTimeout(async () => {
        if (!isMounted.current) return;
        try {
          const detail = await getJob(jobId, sessionId);
          // Record if we've observed any active stage
          if (detail.status === 'processing' || (detail.status as any) === 'extracting' || (detail.status as any) === 'llm') {
            seenActiveStageRef.current.add(jobId);
          }

          // If backend jumped straight to 'done' and we haven't shown any active stage, simulate a brief 'processing' transition
          if (detail.status === 'done' && !seenActiveStageRef.current.has(jobId)) {
            setJobs((prev: JobItem[]) =>
              prev.map((j: JobItem) =>
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
            window.setTimeout(() => {
              if (!isMounted.current) return;
              setJobs((prev: JobItem[]) =>
                prev.map((j: JobItem) =>
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
            return;
          }
          const displayStatus: JobStatus =
            detail.status === 'queued' && seenActiveStageRef.current.has(jobId)
              ? ('processing' as JobStatus)
              : (detail.status as JobStatus);

          setJobs((prev: UiJob[]) =>
            prev.map((j: JobItem) =>
              j.jobId === jobId
                ? {
                    ...j,
                    status: displayStatus,
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
            // Capture and surface backend error, then stop polling
            setJobs((prev: UiJob[]) =>
              prev.map((j: UiJob) =>
                j.jobId === jobId
                  ? { ...j, status: 'failed' as JobStatus, error: (detail as any).error }
                  : j
              )
            );
            const errMsg = String((detail as any)?.error || 'Processing failed');
            toast({ title: 'Processing failed', description: errMsg, variant: 'destructive' as any });
            return;
          } else {
            schedulePoll(jobId, attempt + 1);
          }
        } catch (e: any) {
          // retry with backoff
          schedulePoll(jobId, attempt + 1);
        }
      }, delay);
    },
    [sessionId]
  );

  const rehydrate = useCallback(async () => {
    if (!sessionId) return;
    try {
      const [cfgRes, jobsRes] = await Promise.allSettled([
        getConfig(),
        listJobs(sessionId),
      ]);
      if (!isMounted.current) return;

      // Apply config if available
      if (cfgRes.status === 'fulfilled') {
        setLimits(cfgRes.value);
      }

      // Apply jobs if available
      if (jobsRes.status === 'fulfilled') {
        const list = jobsRes.value;
        setJobs(list.jobs);
        // Fetch details for each job to collect completed results and kick off polling for pending
        await Promise.all(
          list.jobs.map(async (j) => {
            try {
              const d = await getJob(j.jobId, sessionId);
              if (!isMounted.current) return;
              // Update job with freshest status, stages, and any missing metadata
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
                schedulePoll(j.jobId, 0);
              } else if (d.status === 'failed') {
                const errMsg = String((d as any)?.error || 'Processing failed');
                toast({ title: 'Processing failed', description: errMsg, variant: 'destructive' as any });
              }
            } catch {
              // If getJob fails, schedule polling anyway
              schedulePoll(j.jobId, 0);
            }
          })
        );
      }

      // If both failed, decide whether to retry quietly or show toast
      if (cfgRes.status === 'rejected' && jobsRes.status === 'rejected') {
        const errCfg: any = (cfgRes as any).reason;
        const errJobs: any = (jobsRes as any).reason;
        const msgCfg = String(errCfg?.message || errCfg || '');
        const msgJobs = String(errJobs?.message || errJobs || '');
        const combined = `${msgCfg} | ${msgJobs}`.trim();
        const isNetwork =
          (errCfg && (errCfg.name === 'TypeError' || msgCfg.toLowerCase().includes('failed to fetch')))
          || (errJobs && (errJobs.name === 'TypeError' || msgJobs.toLowerCase().includes('failed to fetch')));
        if (isNetwork) {
          if (!isMounted.current) return;
          window.setTimeout(() => {
            if (!isMounted.current) return;
            rehydrate();
          }, 600);
        } else {
          toast({ title: 'Failed to load config or jobs', description: combined || 'Unknown error', variant: 'destructive' as any });
        }
      } else if (jobsRes.status === 'rejected') {
        // Jobs failed but config succeeded — app can still render uploads; retry jobs quietly
        const errJobs: any = (jobsRes as any).reason;
        const msgJobs = String(errJobs?.message || errJobs || '');
        const isNetwork = (errJobs && (errJobs.name === 'TypeError' || msgJobs.toLowerCase().includes('failed to fetch')));
        if (!isMounted.current) return;
        window.setTimeout(() => {
          if (!isMounted.current) return;
          rehydrate();
        }, isNetwork ? 600 : 1000);
      }
    } catch (err: any) {
      const msg = String(err?.message || err);
      const isNetwork = (err && (err.name === 'TypeError' || msg.toLowerCase().includes('failed to fetch')));
      if (isNetwork) {
        if (!isMounted.current) return;
        window.setTimeout(() => {
          if (!isMounted.current) return;
          rehydrate();
        }, 600);
      } else {
        toast({ title: 'Failed to load config or jobs', description: msg, variant: 'destructive' as any });
      }
    }
  }, [sessionId, schedulePoll, toast]);

  useEffect(() => {
    rehydrate();
  }, [rehydrate]);

  const handleFilesAdded = useCallback(
    async (files: File[]) => {
      if (!sessionId) return;
      try {
        const resp = await createJobs(files, sessionId);
        setJobs((prev: JobItem[]) => [...resp.jobs, ...prev]);
        if (resp.note) {
          toast({ title: 'Notice', description: resp.note });
        }
        resp.jobs.forEach((j) => {
          schedulePoll(j.jobId, 0);
          // Shorten the visual 'Queued' duration with a brief, optimistic transition to 'Processing'
          window.setTimeout(() => {
            if (!isMounted.current) return;
            setJobs((prev: JobItem[]) =>
              prev.map((it: JobItem) => {
                if (it.jobId !== j.jobId) return it;
                if (it.status === 'queued' || it.status === 'uploaded') {
                  // mark as seen active to avoid later 'done' -> simulated processing bounce
                  seenActiveStageRef.current.add(j.jobId);
                  return { ...it, status: 'processing' as JobStatus };
                }
                return it;
              })
            );
          }, 300);
        });
      } catch (err: any) {
        toast({ title: 'Upload failed', description: String(err?.message || err), variant: 'destructive' as any });
      }
    },
    [sessionId, schedulePoll, toast]
  );

  const handleRetryJob = useCallback(
    async (jobId: string) => {
      if (!sessionId) return;
      try {
        await retryJob(jobId, sessionId);
        setJobs((prev: JobItem[]) => prev.map((j: JobItem) => (j.jobId === jobId ? { ...j, status: 'queued' as JobStatus } : j)));
        schedulePoll(jobId, 0);
        // As with fresh uploads, shorten the queued visual state on retries
        window.setTimeout(() => {
          if (!isMounted.current) return;
          setJobs((prev: JobItem[]) =>
            prev.map((it: JobItem) => {
              if (it.jobId !== jobId) return it;
              if (it.status === 'queued' || it.status === 'uploaded') {
                seenActiveStageRef.current.add(jobId);
                return { ...it, status: 'processing' as JobStatus };
              }
              return it;
            })
          );
        }, 300);
      } catch (err: any) {
        toast({ title: 'Retry failed', description: String(err?.message || err), variant: 'destructive' as any });
      }
    },
    [sessionId, schedulePoll, toast]
  );

  const handleClearSession = useCallback(async () => {
    if (!sessionId) return;
    try {
      await deleteSession(sessionId);
    } catch (err: any) {
      // proceed even if delete fails, but show feedback
      toast({ title: 'Session cleanup encountered issues', description: String(err?.message || err) });
    }
    const newSid = resetSessionId();
    setSessionId(newSid);
    setJobs([]);
    setResults([]);
    toast({ title: 'Session Cleared', description: 'All invoice jobs have been removed.' });
    // fetch fresh config for new session
    setTimeout(() => {
      // slight delay to ensure session propagated
      rehydrate();
    }, 100);
  }, [rehydrate, sessionId, toast]);

  const handleExport = useCallback(() => {
    if (!sessionId) return;
    exportCsv(sessionId).catch((err) =>
      toast({ title: 'Export failed', description: String(err?.message || err), variant: 'destructive' as any })
    );
  }, [sessionId, toast]);

  const hasResults = results.length > 0;

  return (
    <div className="flex flex-col min-h-screen bg-background">
      <header className="sticky top-0 z-10 bg-background/80 backdrop-blur-sm border-b">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-2">
              <Sparkles className="h-6 w-6 text-primary" />
              <h1 className="text-md font-bold font-headline text-primary">AI Powered Invoice Processing</h1>
            </div>
            <TooltipProvider>
              <div className="flex items-center gap-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={toggleTheme}
                      aria-label="Toggle theme"
                      className="hover:bg-primary/20"
                    >
                      {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>light/dark mode</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={handleClearSession}
                      aria-label="Clear session"
                      className="hover:bg-primary/20"
                    >
                      <RefreshCcw className="h-5 w-5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>restart session</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <a
                      href="https://github.com/fdemirciler/AI-invoice-processing"
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label="Open GitHub repository"
                      className="inline-flex h-10 w-10 items-center justify-center rounded-md hover:bg-primary/20"
                      title="GitHub"
                    >
                      <Github className="h-5 w-5" />
                    </a>
                  </TooltipTrigger>
                  <TooltipContent>GitHub</TooltipContent>
                </Tooltip>
              </div>
            </TooltipProvider>
          </div>
        </div>
      </header>

      <main className="flex-1 container mx-auto p-4 sm:p-6 lg:p-8">
        <div className="space-y-6">
          <SmartHub jobs={jobs} limits={limits} onFilesAdded={handleFilesAdded} onRetry={handleRetryJob} />
          {hasResults && <ResultsTable results={results} onExport={handleExport} />}
        </div>
      </main>
    </div>
  );
}
