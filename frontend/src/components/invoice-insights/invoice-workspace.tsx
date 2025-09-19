"use client";

import React from 'react';
import { SmartHub } from '@/components/invoice-insights/smart-hub';
import { ResultsTable } from '@/components/invoice-insights/results-table';

type SmartHubProps = React.ComponentProps<typeof SmartHub>;
type ResultsTableProps = React.ComponentProps<typeof ResultsTable>;

interface InvoiceWorkspaceProps {
  jobs: SmartHubProps['jobs'];
  limits: SmartHubProps['limits'];
  onFilesAdded: SmartHubProps['onFilesAdded'];
  onRetry: SmartHubProps['onRetry'];
  bannerText?: SmartHubProps['bannerText'];
  disableUpload?: SmartHubProps['disableUpload'];
  disableRetry?: SmartHubProps['disableRetry'];
  results: ResultsTableProps['results'];
  onExport?: ResultsTableProps['onExport'];
}

export function InvoiceWorkspace({
  jobs,
  limits,
  onFilesAdded,
  onRetry,
  bannerText = '',
  disableUpload = false,
  disableRetry = false,
  results,
  onExport,
}: InvoiceWorkspaceProps) {
  const hasResults = Array.isArray(results) && results.length > 0;
  return (
    <>
      <div id="upload-area" />
      <SmartHub
        jobs={jobs}
        limits={limits}
        onFilesAdded={onFilesAdded}
        onRetry={onRetry}
        bannerText={bannerText}
        disableUpload={disableUpload}
        disableRetry={disableRetry}
      />
      {hasResults && <ResultsTable results={results} onExport={onExport} />}
    </>
  );
}
