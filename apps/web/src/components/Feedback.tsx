import { AlertTriangle, Inbox, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

export function ErrorAlert({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <p>{message}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon: Icon = Inbox,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: LucideIcon;
}) {
  return (
    <div className="flex min-h-72 flex-col items-center justify-center px-6 text-center">
      <span className="mb-4 rounded-xl bg-ink-100 p-3 text-ink-500 dark:bg-ink-800 dark:text-ink-300">
        <Icon className="size-6" aria-hidden="true" />
      </span>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-1 max-w-md text-sm leading-6 text-ink-500 dark:text-ink-400">
        {description}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
