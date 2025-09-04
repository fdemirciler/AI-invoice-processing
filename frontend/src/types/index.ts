export type JobStatus = 'processing' | 'done' | 'failed';

export interface InvoiceData {
  invoiceNumber: string;
  vendor: string;
  date: string;
  total: number;
}

export interface Job {
  id: string;
  file: File;
  status: JobStatus;
  processingStartedAt?: number;
  result?: InvoiceData;
  error?: string;
}
