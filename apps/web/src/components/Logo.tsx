import { FileSearch } from 'lucide-react';

export function Logo() {
  return (
    <div className="flex items-center gap-2.5" aria-label="GroundedPDF">
      <span className="flex size-9 items-center justify-center rounded-lg bg-accent-700 text-white dark:bg-accent-500 dark:text-ink-950">
        <FileSearch className="size-5" aria-hidden="true" />
      </span>
      <span className="text-base font-bold tracking-tight">
        Grounded<span className="text-accent-700 dark:text-accent-400">PDF</span>
      </span>
    </div>
  );
}
