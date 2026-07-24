import { AlertCircle, CheckCircle2, Clock3, LoaderCircle } from 'lucide-react';
import type { ProcessingStatus } from '../types/api';

const styles: Record<ProcessingStatus, string> = {
  queued: 'bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-200',
  processing: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  ready: 'bg-accent-100 text-accent-800 dark:bg-accent-950 dark:text-accent-200',
  failed: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200',
  deleted: 'bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-300',
};

export function StatusBadge({ status }: { status: ProcessingStatus }) {
  const Icon =
    status === 'ready'
      ? CheckCircle2
      : status === 'failed'
        ? AlertCircle
        : status === 'processing'
          ? LoaderCircle
          : Clock3;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${styles[status]}`}
    >
      <Icon
        className={`size-3.5 ${status === 'processing' ? 'animate-spin' : ''}`}
        aria-hidden="true"
      />
      {status}
    </span>
  );
}
