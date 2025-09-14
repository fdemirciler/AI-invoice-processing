"use client";

import type { DragEvent, ChangeEvent } from 'react';
import React, { useRef } from 'react';
import { UploadCloud, FileText, Loader2, CheckCircle2, XCircle, RefreshCcw, List, HelpCircle } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useRateLimitContext } from '@/context/rate-limit-context';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Progress } from '@/components/ui/progress';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import type { JobStatus, Limits } from '@/types/api';

type SmartHubJob = {
  jobId: string;
  filename: string;
  status: JobStatus;
  sizeBytes?: number;
  pageCount?: number;
  stages?: Record<string, string>;
  error?: string;
};

interface SmartHubProps {
  jobs: SmartHubJob[];
  limits: Limits | null;
  onFilesAdded: (files: File[]) => void;
  onRetry: (jobId: string) => void;
  bannerText?: string;
  disableUpload?: boolean;
  disableRetry?: boolean;
}

const formatKb = (bytes?: number) => {
  if (!bytes && bytes !== 0) return '';
  return `${Math.round(bytes / 1024)} KB`;
};

const formatPages = (pages?: number) => {
  if (pages === undefined || pages === null) return '';
  const n = Number(pages);
  if (!Number.isFinite(n)) return '';
  return `${n} ${n === 1 ? 'page' : 'pages'}`;
};

const truncate = (s?: string, n = 160) => {
  if (!s) return '';
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
};

const simpleLabel = (status: JobStatus): 'Queued' | 'Processing' | 'Done' | 'Failed' => {
  if (status === 'done') return 'Done';
  if (status === 'failed') return 'Failed';
  if (status === 'queued' || status === 'uploaded') return 'Queued';
  // extracting, llm, processing -> Processing
  return 'Processing';
};

const StatusIndicator = ({ status }: { status: JobStatus }) => {
  const label = simpleLabel(status);
  switch (label) {
    case 'Processing':
      return (
        <Badge
          variant="secondary"
          className="bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-300"
        >
          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
          Processing
        </Badge>
      );
    case 'Done':
      return (
        <Badge
          variant="secondary"
          className="bg-green-200 text-green-900 dark:bg-green-900/30 dark:text-green-200"
        >
          <CheckCircle2 className="mr-1 h-3 w-3" />
          Done
        </Badge>
      );
    case 'Failed':
      return (
        <Badge variant="destructive">
          <XCircle className="mr-1 h-3 w-3" />
          Failed
        </Badge>
      );
    default:
      return <Badge variant="outline">Queued</Badge>;
  }
};

const stageOrder = ['uploaded', 'queued', 'processing', 'extracting', 'llm', 'done'] as const;

function progressFromStages(stages: Record<string, string> | undefined, status: JobStatus): number {
  // Failed jobs do not show progress; return 0 to render nothing upstream
  if (status === 'failed') return 0;

  // Determine current stage primarily from status (backend sets status reliably)
  const statusAsStage = ((): (typeof stageOrder)[number] | null => {
    switch (status) {
      case 'uploaded':
      case 'queued':
      case 'processing':
      case 'extracting':
      case 'llm':
      case 'done':
        return status as any;
      default:
        return null;
    }
  })();

  let idx = statusAsStage ? stageOrder.indexOf(statusAsStage) : -1;

  // If status is not one of the ordered stages, infer from the single key in stages map
  if (idx < 0 && stages && Object.keys(stages).length > 0) {
    const keys = Object.keys(stages) as (typeof stageOrder[number])[];
    const known = keys.find((k) => stageOrder.includes(k));
    if (known) idx = stageOrder.indexOf(known);
  }

  if (idx < 0) {
    // Fallback heuristics
    if (status === 'done') return 100;
    if (status === 'queued' || status === 'uploaded') return 16;
    return 50;
  }

  const pct = Math.round(((idx + 1) / stageOrder.length) * 100);
  return Math.min(100, Math.max(0, pct));
}


export function SmartHub({ jobs, limits, onFilesAdded, onRetry, bannerText, disableUpload = false, disableRetry = false }: SmartHubProps) {
  const [isDragActive, setIsDragActive] = React.useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();
  const { showRateLimit } = useRateLimitContext();

  const handleDrag = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragActive(true);
    } else if (e.type === 'dragleave') {
      setIsDragActive(false);
    }
  };
  
  const validateAndAddFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    if (disableUpload) return;

    const files = Array.from(fileList);
    const validFiles: File[] = [];

    if (limits && files.length > limits.maxFiles) {
      showRateLimit({
        title: 'Upload limit exceeded',
        description: `You can only upload a maximum of ${limits.maxFiles} files at a time. Please select fewer files.`,
        retryAfterSec: 0, // No cooldown for file count validation
      });
      return;
    }
    
    for (const file of files) {
      const mimeOk = !limits?.acceptedMime?.length
        ? file.type === 'application/pdf'
        : limits.acceptedMime.includes(file.type);
      if (!mimeOk) {
        toast({
          variant: 'warning',
          title: 'Invalid file type',
          description: `File "${file.name}" is not a PDF.`,
          duration: 5000,
        });
        continue;
      }
      const maxBytes = (limits?.maxSizeMb ?? 10) * 1024 * 1024;
      if (file.size > maxBytes) {
        toast({
          variant: 'warning',
          title: 'File too large',
          description: `File "${file.name}" exceeds the ${limits?.maxSizeMb ?? 10}MB size limit.`,
          duration: 5000,
        });
        continue;
      }
      validFiles.push(file);
    }

    if (validFiles.length > 0) {
      onFilesAdded(validFiles);
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    if (disableUpload) return;
    validateAndAddFiles(e.dataTransfer.files);
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (disableUpload) return;
    validateAndAddFiles(e.target.files);
     if (e.target) {
      e.target.value = '';
    }
  };
  
  const onButtonClick = () => {
    if (disableUpload) return;
    inputRef.current?.click();
  };
  
  const totalJobs = jobs.length;
  const processingJobs = jobs.filter(j => j.status !== 'done' && j.status !== 'failed').length;
  const allDone = totalJobs > 0 && jobs.every((j) => j.status === 'done');

  // Slightly taller rows to accommodate the progress bar
  const scrollAreaHeight = totalJobs > 0 ? Math.min(totalJobs * 92, 300) : 256;


  return (
    <Card className="w-full max-w-3xl mx-auto">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
            {totalJobs > 0 && <List className="w-5 h-5" />}
            {totalJobs > 0 ? (allDone ? "Processed" : "Processing...") : "Upload Invoices"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {bannerText && (
          <div
            role="status"
            aria-live="polite"
            className="mb-3 rounded-md border border-yellow-300 bg-yellow-50 text-yellow-900 dark:bg-yellow-900/20 dark:text-yellow-200 px-3 py-2 text-sm"
          >
            {bannerText}
          </div>
        )}
        {jobs.length === 0 ? (
            <form 
              className="w-full"
              onSubmit={(e) => e.preventDefault()}
            >
              <input
                ref={inputRef}
                id="dropzone-file"
                type="file"
                className="hidden"
                multiple={true}
                onChange={handleChange}
                accept="application/pdf"
                disabled={disableUpload}
              />
              <div
                className={cn(
                  "relative flex flex-col items-center justify-center w-full h-64 border-2 border-dashed rounded-lg cursor-pointer bg-card hover:bg-muted transition-colors duration-300",
                  isDragActive ? "border-primary" : "border-border",
                  disableUpload && "opacity-60 cursor-not-allowed"
                )}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={onButtonClick}
                aria-disabled={disableUpload}
              >
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  <UploadCloud className={cn("w-10 h-10 mb-4 text-muted-foreground", isDragActive && "text-primary")} />
                  <p className="mb-2 text-sm text-muted-foreground">
                    <span className="font-semibold text-primary">Drag & Drop Invoices Here</span> or Click to Browse
                  </p>
                  <p className="text-xs text-muted-foreground">
                    PDF only{limits ? ` (max ${limits.maxSizeMb}MB, up to ${limits.maxFiles} files, ≤ ${limits.maxPages} pages)` : ''}
                  </p>
                </div>
              </div>
            </form>
        ) : (
            <ScrollArea 
                className="pr-4"
                style={{ height: `${scrollAreaHeight}px` }}
            >
                <div className="space-y-4">
                {jobs.map((job) => (
                    <div
                    key={job.jobId}
                    className={cn(
                        "flex items-center space-x-4 p-3 bg-card rounded-lg border transition-opacity",
                        job.status === 'done' && 'opacity-60'
                    )}
                    >
                    <FileText className="h-6 w-6 text-muted-foreground flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 min-w-0">
                          <p
                            className="text-sm font-medium text-foreground truncate"
                            title={job.filename}
                          >
                            {job.filename}
                          </p>
                          <span className="text-xs text-muted-foreground flex-shrink-0">
                            {[
                              job.sizeBytes !== undefined ? formatKb(job.sizeBytes) : null,
                              job.pageCount !== undefined ? formatPages(job.pageCount) : null,
                            ]
                              .filter(Boolean)
                              .join(' · ')}
                          </span>
                        </div>
                        {job.status !== 'failed' ? (
                          <div className="mt-2">
                            <div className="flex items-center justify-end mb-1">
                              <span className="text-xs text-muted-foreground">
                                {progressFromStages(job.stages, job.status)}%
                              </span>
                            </div>
                            <Progress value={progressFromStages(job.stages, job.status)} className="h-2" />
                          </div>
                        ) : (
                          <div className="mt-2 flex items-start gap-1">
                            <p className="text-xs text-red-600 dark:text-red-400 break-words flex-1">
                              {truncate(job.error ?? 'Processing failed')}
                            </p>
                            {job.error && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <button
                                      type="button"
                                      className="p-1 text-red-600 dark:text-red-400 hover:opacity-80"
                                      aria-label="Show error details"
                                    >
                                      <HelpCircle className="h-4 w-4" />
                                    </button>
                                  </TooltipTrigger>
                                  <TooltipContent className="max-w-xs whitespace-pre-wrap break-words">
                                    {job.error}
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}
                          </div>
                        )}
                    </div>
                    <div className="flex items-center space-x-2">
                        <StatusIndicator status={job.status} />
                        {job.status === 'failed' && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => onRetry(job.jobId)}
                            disabled={disableRetry}
                            aria-label={`Retry processing ${job.filename}`}
                        >
                            <RefreshCcw className="h-4 w-4" />
                        </Button>
                        )}
                    </div>
                    </div>
                ))}
                </div>
            </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
