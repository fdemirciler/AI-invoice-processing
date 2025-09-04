// Shared API types aligned with backend models

export type JobStatus =
  | 'uploaded'
  | 'queued'
  | 'processing'
  // Intermediate backend statuses we map to "processing" in the UI
  | 'extracting'
  | 'llm'
  | 'done'
  | 'failed';

export interface Limits {
  maxFiles: number;
  maxSizeMb: number;
  maxPages: number;
  acceptedMime?: string[];
}

export interface JobItem {
  jobId: string;
  filename: string;
  status: JobStatus;
  stages?: Record<string, string>;
  sizeBytes?: number;
  pageCount?: number;
}

export interface JobsCreateResponse {
  sessionId: string;
  jobs: JobItem[];
  limits: Limits;
  note?: string | null;
}

export interface JobDetail {
  jobId: string;
  status: JobStatus;
  stages?: Record<string, string>;
  resultJson?: any;
  confidenceScore?: number;
  error?: string;
  sizeBytes?: number;
  pageCount?: number;
}

export interface ListJobsResponse {
  sessionId: string;
  jobs: JobItem[];
}

// Minimal display projection used by the table
export interface InvoiceDisplay {
  invoiceNumber: string;
  vendorName: string;
  invoiceDate: string; // ISO string
  total: number;
  jobId?: string;
}
