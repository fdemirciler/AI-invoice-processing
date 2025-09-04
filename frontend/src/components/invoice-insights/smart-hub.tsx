"use client";

import type { DragEvent, ChangeEvent } from 'react';
import React, { useRef } from 'react';
import { UploadCloud, FileText, Loader2, CheckCircle2, XCircle, RefreshCcw, List } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { JobStatus, Limits } from '@/types/api';

type SmartHubJob = {
  jobId: string;
  filename: string;
  status: JobStatus;
  sizeBytes?: number;
};

interface SmartHubProps {
  jobs: SmartHubJob[];
  limits: Limits | null;
  onFilesAdded: (files: File[]) => void;
  onRetry: (jobId: string) => void;
}

const formatKb = (bytes?: number) => {
  if (!bytes && bytes !== 0) return '';
  return `${Math.round(bytes / 1024)} KB`;
};

const StatusIndicator = ({ status }: { status: JobStatus }) => {
  switch (status) {
    case 'processing':
      return <Badge variant="secondary" className="bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-300"><Loader2 className="mr-1 h-3 w-3 animate-spin" />Processing</Badge>;
    case 'done':
      return <Badge variant="secondary" className="bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-300"><CheckCircle2 className="mr-1 h-3 w-3" />Done</Badge>;
    case 'failed':
      return <Badge variant="destructive"><XCircle className="mr-1 h-3 w-3" />Failed</Badge>;
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
};


export function SmartHub({ jobs, limits, onFilesAdded, onRetry }: SmartHubProps) {
  const [isDragActive, setIsDragActive] = React.useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

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

    const files = Array.from(fileList);
    const validFiles: File[] = [];

    if (limits && files.length > limits.maxFiles) {
      toast({
        variant: 'destructive',
        title: 'Too many files',
        description: `You can only upload a maximum of ${limits.maxFiles} files at a time.`,
      });
      return;
    }
    
    for (const file of files) {
      const mimeOk = !limits?.acceptedMime?.length
        ? file.type === 'application/pdf'
        : limits.acceptedMime.includes(file.type);
      if (!mimeOk) {
        toast({
          variant: 'destructive',
          title: 'Invalid file type',
          description: `File "${file.name}" is not a PDF.`,
        });
        continue;
      }
      const maxBytes = (limits?.maxSizeMb ?? 10) * 1024 * 1024;
      if (file.size > maxBytes) {
        toast({
          variant: 'destructive',
          title: 'File too large',
          description: `File "${file.name}" exceeds the ${limits?.maxSizeMb ?? 10}MB size limit.`,
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
    validateAndAddFiles(e.dataTransfer.files);
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    validateAndAddFiles(e.target.files);
     if (e.target) {
      e.target.value = '';
    }
  };
  
  const onButtonClick = () => {
    inputRef.current?.click();
  };
  
  const totalJobs = jobs.length;
  const processingJobs = jobs.filter(j => j.status !== 'done' && j.status !== 'failed').length;

  const scrollAreaHeight = totalJobs > 0 ? Math.min(totalJobs * 76, 256) : 256;


  return (
    <Card className="w-full max-w-3xl mx-auto">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
            {totalJobs > 0 && <List className="w-5 h-5" />}
            {totalJobs > 0 ? "Processing..." : "Upload Invoices"}
        </CardTitle>
      </CardHeader>
      <CardContent>
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
              />
              <div
                className={cn(
                  "relative flex flex-col items-center justify-center w-full h-64 border-2 border-dashed rounded-lg cursor-pointer bg-card hover:bg-muted transition-colors duration-300",
                  isDragActive ? "border-primary" : "border-border",
                )}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={onButtonClick}
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
                        <p className="text-sm font-medium text-foreground truncate" title={job.filename}>
                        {job.filename}
                        </p>
                        <p className="text-xs text-muted-foreground">
                        {formatKb(job.sizeBytes)}
                        </p>
                    </div>
                    <div className="flex items-center space-x-2">
                        <StatusIndicator status={job.status} />
                        {job.status === 'failed' && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => onRetry(job.jobId)}
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
