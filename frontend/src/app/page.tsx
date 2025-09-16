"use client";

import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { ResultsTable } from '@/components/invoice-insights/results-table';
// MessageCenter and inline banners removed in favor of unified toasts
import { Moon, Sun, RefreshCcw, Github, HelpCircle, Zap } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { SmartHub } from '@/components/invoice-insights/smart-hub';
import type { HttpError } from '@/lib/api';
import { useSession } from '@/hooks/useSession';
import { useConfig } from '@/hooks/useConfig';
import { useJobs } from '@/hooks/useJobs';
import { Frontpage } from '@/components/marketing/frontpage';


// --- Main Component ---
export default function Home() {
  const { sessionId, resetSession } = useSession();
  const { limits, error: configError, reload: reloadConfig } = useConfig(true);
  const { jobs, results, onFilesAdded, onRetry, onClearSession, onExport, rehydrate } = useJobs();
  const [theme, setTheme] = useState('dark');
  const { toast } = useToast();
  // Control disabling during rate-limit events
  const [disableUpload, setDisableUpload] = useState(false);
  const [disableRetry, setDisableRetry] = useState(false);
  const [showFrontpage, setShowFrontpage] = useState(true);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    setTheme(savedTheme);
  }, []);

  useEffect(() => {
    document.documentElement.className = theme;
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme((prev: string) => (prev === 'dark' ? 'light' : 'dark'));

  // Load jobs when session changes
  useEffect(() => {
    if (sessionId) void rehydrate(sessionId);
  }, [sessionId, rehydrate]);

  // Initialize frontpage visibility from URL/localStorage
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const force = params.get('frontpage');
      if (force === '1') {
        setShowFrontpage(true);
        return;
      }
      const dismissed = localStorage.getItem('frontpageDismissed');
      setShowFrontpage(dismissed === '1' ? false : true);
    } catch {}
  }, []);

  // Surface config errors via toast; optionally retry on transient network errors
  useEffect(() => {
    if (!configError) return;
    const msg = String(configError || '');
    toast({ title: 'Failed to load config', description: msg, variant: 'destructive' as any });
    if (msg.toLowerCase().includes('failed to fetch')) {
      setTimeout(() => reloadConfig().catch(() => {}), 600);
    }
  }, [configError, reloadConfig, toast]);

  // Auto-hide frontpage if any jobs/results exist
  useEffect(() => {
    if (showFrontpage && (jobs.length > 0 || results.length > 0)) {
      setShowFrontpage(false);
      try { localStorage.setItem('frontpageDismissed', '1'); } catch {}
    }
  }, [jobs.length, results.length, showFrontpage]);

  const handleFilesAdded = useCallback(async (files: File[]) => {
    if (!sessionId) return;
    try {
      const resp = await onFilesAdded(files, sessionId);
      if (resp?.note) {
        toast({ title: 'Notice', description: resp.note, duration: 5000 });
      }
    } catch (err: any) {
      if ((err as any)?.status === 429) {
        const he = err as HttpError;
        const retryAfter = he.rateLimit?.retryAfterSec ?? 0;
        setDisableUpload(true);
        setTimeout(() => setDisableUpload(false), (retryAfter || 1) * 1000);
        const max = limits?.maxFiles ?? 5;
        toast({ title: `Up to ${max} files can be uploaded`, variant: 'warning' as any, duration: 5000 });
        return;
      }
      toast({ title: 'Upload failed', description: String(err?.message || err), variant: 'destructive' as any, duration: 5000 });
    }
  }, [sessionId, onFilesAdded, limits, toast]);

  const handleRetryJob = useCallback(async (jobId: string) => {
    if (!sessionId) return;
    try {
      await onRetry(jobId, sessionId);
    } catch (err: any) {
      if ((err as any)?.status === 429) {
        const he = err as HttpError;
        const detail = (he.detail || '').toLowerCase();
        if (detail.includes('retry limit')) return;
        const retryAfter = he.rateLimit?.retryAfterSec ?? 0;
        setDisableRetry(true);
        setTimeout(() => setDisableRetry(false), (retryAfter || 1) * 1000);
        const max = limits?.maxFiles ?? 5;
        toast({ title: `Up to ${max} files can be uploaded`, variant: 'warning' as any, duration: 5000 });
        return;
      }
      toast({ title: 'Retry failed', description: String(err?.message || err), variant: 'destructive' as any, duration: 5000 });
    }
  }, [sessionId, onRetry, limits, toast]);

  const handleClearSession = useCallback(async () => {
    if (!sessionId) return;
    try {
      await onClearSession(sessionId);
    } catch (err: any) {
      toast({ title: 'Session cleanup encountered issues', description: String(err?.message || err), variant: 'destructive' as any, duration: 5000 });
    }
    resetSession();
    toast({ title: 'Session Cleared', description: 'All invoice jobs have been removed.', duration: 5000 });
  }, [onClearSession, resetSession, sessionId, toast]);

  const handleExport = useCallback(() => {
    if (!sessionId) return;
    onExport(sessionId).catch((err) =>
      toast({ title: 'Export failed', description: String(err?.message || err), variant: 'destructive' as any, duration: 5000 })
    );
  }, [sessionId, onExport, toast]);

  const hasResults = results.length > 0;
  const maxFiles = limits?.maxFiles ?? '-';
  const maxSizeMb = limits?.maxSizeMb ?? '-';
  const maxPages = limits?.maxPages ?? '-';

  const handleStartFrontpage = useCallback(() => {
    setShowFrontpage(false);
    try { localStorage.setItem('frontpageDismissed', '1'); } catch {}
    setTimeout(() => {
      const el = document.getElementById('upload-area');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        const focusable = el.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])') as HTMLElement | null;
        focusable?.focus();
      }
    }, 50);
  }, []);

  return (
    <div className="flex flex-col min-h-screen bg-background">
      <header className="sticky top-0 z-10 bg-background/80 backdrop-blur-sm border-b">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-2">
              <Zap className="h-6 w-6 text-primary" />
              <h1 className="text-md font-bold font-headline text-primary">AI Powered Invoice Processing</h1>
            </div>
            <TooltipProvider>
              <div className="flex items-center gap-2">
                {/* Help dialog */}
                <Dialog>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <DialogTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Help"
                          className="hover:bg-primary/20"
                        >
                          <HelpCircle className="h-5 w-5" />
                        </Button>
                      </DialogTrigger>
                    </TooltipTrigger>
                    <TooltipContent>help & about</TooltipContent>
                  </Tooltip>
                  <DialogContent className="max-w-lg">
                    <DialogHeader>
                      <DialogTitle>About This App</DialogTitle>
                    </DialogHeader>
                    <Accordion type="single" collapsible className="mt-4">
                      <AccordionItem value="limits">
                        <AccordionTrigger>Usage Limits</AccordionTrigger>
                        <AccordionContent>
                          <ul className="list-disc pl-5 space-y-1">
                            <li>Max files per upload: <strong>{maxFiles}</strong></li>
                            <li>Max file size: <strong>{maxSizeMb}</strong> MB</li>
                            <li>Max pages per PDF: <strong>{maxPages}</strong></li>
                          </ul>
                        </AccordionContent>
                      </AccordionItem>
                      <AccordionItem value="privacy">
                        <AccordionTrigger>Privacy & Security</AccordionTrigger>
                        <AccordionContent>
                          Your files are processed securely and are automatically deleted once your session ends or when you clear data. Nothing is stored permanently.
                        </AccordionContent>
                      </AccordionItem>
                      <AccordionItem value="tech">
                        <AccordionTrigger>Technology</AccordionTrigger>
                        <AccordionContent>
                          Powered by <strong>Google Cloud Vision</strong> for OCR and <strong>Gemini AI</strong> for structured data extraction.
                        </AccordionContent>
                      </AccordionItem>
                    </Accordion>
                  </DialogContent>
                </Dialog>
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
          {/* Unified toasts handle all messages now */}
          {showFrontpage ? (
            <Frontpage limits={limits} onStart={handleStartFrontpage} />
          ) : (
            <>
              <div id="upload-area" />
              <SmartHub
                jobs={jobs}
                limits={limits}
                onFilesAdded={handleFilesAdded}
                onRetry={handleRetryJob}
                bannerText={''}
                disableUpload={disableUpload}
                disableRetry={disableRetry}
              />
              {hasResults && <ResultsTable results={results} onExport={handleExport} />}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
