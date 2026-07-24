import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ExternalLink, FileText, RotateCw, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { Link, useLocation } from 'react-router';
import { api } from '../../api/client';
import { Skeleton } from '../../components/Skeleton';
import type { VerificationSentence, VerificationVerdict } from '../../types/api';
import { highlightParamValue } from '../../utils/highlight';

const VERDICT_ORDER: Record<VerificationVerdict, number> = {
  unsupported: 0,
  weak: 1,
  supported: 2,
};

const VERDICT_LABEL: Record<VerificationVerdict, string> = {
  unsupported: 'Not found',
  weak: 'Weak match',
  supported: 'Supported',
};

/* Mirrors the StatusBadge red/amber/green usage; AA contrast in both themes. */
const VERDICT_STYLE: Record<VerificationVerdict, string> = {
  unsupported: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200',
  weak: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  supported: 'bg-accent-100 text-accent-800 dark:bg-accent-950 dark:text-accent-200',
};

function sortSentences(sentences: VerificationSentence[]): VerificationSentence[] {
  // Stable sort: unsupported claims are the headline, then weak, then supported.
  return [...sentences].sort((a, b) => VERDICT_ORDER[a.verdict] - VERDICT_ORDER[b.verdict]);
}

function SentenceRow({ sentence }: { sentence: VerificationSentence }) {
  const location = useLocation();
  return (
    <li className="rounded-lg border bg-ink-50 p-3 dark:bg-ink-950">
      <div className="flex items-start gap-2.5">
        <span
          className={`mt-0.5 shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${VERDICT_STYLE[sentence.verdict]}`}
        >
          {VERDICT_LABEL[sentence.verdict]}
        </span>
        <p className="min-w-0 text-sm leading-6 text-ink-800 dark:text-ink-100">{sentence.text}</p>
      </div>
      {sentence.source ? (
        <Link
          to={`/documents/${sentence.source.document_id}/view?page=${sentence.source.page_number}&highlight=${encodeURIComponent(highlightParamValue(sentence.source.excerpt))}`}
          state={{ returnTo: location.pathname, highlight: sentence.source.excerpt }}
          className="group mt-2 inline-flex max-w-full items-center gap-1.5 rounded text-xs font-medium text-ink-600 hover:text-accent-700 dark:text-ink-300 dark:hover:text-accent-400"
          aria-label={`Open evidence in ${sentence.source.document_name} page ${sentence.source.page_number}`}
        >
          <FileText className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="truncate">{sentence.source.document_name}</span>
          <span className="shrink-0">· p. {sentence.source.page_number}</span>
          <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
        </Link>
      ) : (
        <p className="mt-2 text-xs text-ink-500 dark:text-ink-400">
          This claim was not found in your documents.
        </p>
      )}
    </li>
  );
}

/**
 * "Verify answer" action plus its inline result panel. A read-only lens over a
 * persisted assistant answer: the API re-scores each sentence against the
 * conversation's documents and nothing about the message is ever changed.
 */
export function VerificationPanel({
  conversationId,
  messageId,
}: {
  conversationId: string;
  messageId: string;
}) {
  const [open, setOpen] = useState(false);
  const verification = useQuery({
    queryKey: ['verification', conversationId, messageId],
    queryFn: () => api.conversations.verify(conversationId, messageId),
    enabled: open,
    staleTime: Infinity,
    retry: false,
  });

  const sentences = verification.data?.sentences ?? [];
  const supported = sentences.filter((sentence) => sentence.verdict === 'supported').length;
  const summary =
    sentences.length > 0
      ? `${supported} of ${sentences.length} claims supported by your documents`
      : 'This answer contains no checkable claims.';

  return (
    <div className="mt-3 border-t pt-3">
      <button
        type="button"
        className="button-ghost -ml-2 px-2 text-xs font-semibold"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <ShieldCheck className="size-4 text-accent-700 dark:text-accent-400" aria-hidden="true" />
        Verify answer
        <ChevronDown
          className={`size-3.5 transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="mt-2">
          {verification.isPending ? (
            <div className="space-y-2" aria-label="Checking claims against your documents">
              <Skeleton className="h-4 w-56" />
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : verification.isError ? (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
              <p role="alert">{verification.error.message}</p>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded font-semibold underline underline-offset-2"
                onClick={() => void verification.refetch()}
              >
                <RotateCw className="size-3.5" aria-hidden="true" /> Retry
              </button>
            </div>
          ) : (
            <>
              <p role="status" className="text-xs font-medium text-ink-600 dark:text-ink-300">
                {summary}
              </p>
              {sentences.length > 0 && (
                <ul className="mt-2 space-y-2">
                  {sortSentences(sentences).map((sentence, index) => (
                    <SentenceRow key={`${sentence.verdict}-${index}`} sentence={sentence} />
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
