import type { JobStatus } from '@/types/api';

export const stageOrder = ['uploaded', 'queued', 'processing', 'extracting', 'llm', 'done'] as const;

export function labelFromStatus(status: JobStatus): 'Uploaded' | 'Queued' | 'Processing' | 'Extracting' | 'Analyzing' | 'Done' | 'Failed' {
  switch (status) {
    case 'uploaded':
      return 'Uploaded';
    case 'queued':
      return 'Queued';
    case 'processing':
      return 'Processing';
    case 'extracting':
      return 'Extracting';
    case 'llm':
      return 'Analyzing';
    case 'done':
      return 'Done';
    case 'failed':
      return 'Failed';
    default:
      return 'Queued';
  }
}

export function progressFromStages(
  stages: Record<string, string> | undefined,
  status: JobStatus
): number {
  // Failed jobs do not show progress
  if (status === 'failed') return 0;

  // Determine current stage primarily from status
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

  // If status is not one of the ordered stages, infer from stages map
  if (idx < 0 && stages && Object.keys(stages).length > 0) {
    const keys = Object.keys(stages) as (typeof stageOrder[number])[];
    const known = keys.find((k) => (stageOrder as readonly string[]).includes(k));
    if (known) idx = stageOrder.indexOf(known);
  }

  if (idx < 0) {
    if (status === 'done') return 100;
    if (status === 'queued' || status === 'uploaded') return 16;
    return 50;
  }

  const pct = Math.round(((idx + 1) / stageOrder.length) * 100);
  return Math.min(100, Math.max(0, pct));
}
