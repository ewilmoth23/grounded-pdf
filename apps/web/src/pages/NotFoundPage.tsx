import { SearchX } from 'lucide-react';
import { Link } from 'react-router';

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-6 py-12">
      <div className="flex flex-col items-center text-center">
        <span className="mb-5 rounded-xl bg-ink-100 p-3 text-ink-500 dark:bg-ink-800 dark:text-ink-300">
          <SearchX className="size-7" aria-hidden="true" />
        </span>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent-700 dark:text-accent-400">
          404
        </p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">Page not found</h1>
        <p className="mt-3 max-w-md text-sm leading-6 text-ink-500 dark:text-ink-400">
          The requested GroundedPDF page does not exist.
        </p>
        <Link className="button-primary mt-6" to="/chat">
          Back to chat
        </Link>
      </div>
    </div>
  );
}
