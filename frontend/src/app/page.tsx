"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { ResultsTable } from '@/components/invoice-insights/results-table';
import { Sparkles, Moon, Sun, RefreshCcw } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { SmartHub } from '@/components/invoice-insights/smart-hub';
import { getOrCreateSessionId, resetSessionId } from '@/lib/session';
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
      jobId: detail.jobId,
    };
  } catch {
    return null;
  }
}


// --- Main Component ---
export default function Home() {
  const [sessionId, setSessionId] = useState<string>('');
  const [limits, setLimits] = useState<Limits | null>(null);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [results, setResults] = useState<InvoiceDisplay[]>([]);
  const [theme, setTheme] = useState('dark');
  const { toast } = useToast();
  const isMounted = useRef(true);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    setTheme(savedTheme);
    const sid = getOrCreateSessionId();
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
      const base = 1000;
      const max = 10000;
      const delay = Math.min(max, Math.floor(base * Math.pow(1.8, attempt))) + Math.floor(Math.random() * 300);
      window.setTimeout(async () => {
        if (!isMounted.current) return;
        try {
          const detail = await getJob(jobId, sessionId);
          setJobs((prev: JobItem[]) => prev.map((j: JobItem) => (j.jobId === jobId ? { ...j, status: detail.status as JobStatus } : j)));
          if (detail.status === 'done') {
            const disp = toDisplay(detail);
            if (disp) {
              setResults((prev: InvoiceDisplay[]) => {
                const exists = prev.some((r: InvoiceDisplay) => r.jobId === disp.jobId);
                return exists ? prev : [disp, ...prev];
              });
            }
          } else if (detail.status === 'failed') {
            // stop polling
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
      const cfg = await getConfig();
      if (!isMounted.current) return;
      setLimits(cfg);
      const list = await listJobs(sessionId);
      if (!isMounted.current) return;
      setJobs(list.jobs);
      // Fetch details for each job to collect completed results and kick off polling for pending
      await Promise.all(
        list.jobs.map(async (j) => {
          try {
            const d = await getJob(j.jobId, sessionId);
            if (!isMounted.current) return;
            if (d.status === 'done') {
              const disp = toDisplay(d);
              if (disp) {
                setResults((prev: InvoiceDisplay[]) => {
                  const exists = prev.some((r: InvoiceDisplay) => r.jobId === disp.jobId);
                  return exists ? prev : [disp, ...prev];
                });
              }
            } else if (d.status !== 'failed') {
              schedulePoll(j.jobId, 0);
            }
          } catch {
            // If getJob fails, schedule polling anyway
            schedulePoll(j.jobId, 0);
          }
        })
      );
    } catch (err: any) {
      toast({ title: 'Failed to load config or jobs', description: String(err?.message || err), variant: 'destructive' as any });
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
        resp.jobs.forEach(j => schedulePoll(j.jobId, 0));
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
              <h1 className="text-md font-bold font-headline text-muted-foreground">Invoice Insights</h1>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
                {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
              </Button>
              <Button variant="ghost" size="icon" onClick={handleClearSession} aria-label="Clear session">
                <RefreshCcw className="h-5 w-5" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 container mx-auto p-4 sm:p-6 lg:p-8">
        <div className="space-y-6">
          <SmartHub jobs={jobs as any} limits={limits} onFilesAdded={handleFilesAdded} onRetry={handleRetryJob} />
          {hasResults && <ResultsTable results={results} onExport={handleExport} />}
        </div>
      </main>
    </div>
  );
}
