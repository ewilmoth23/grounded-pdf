import { ChevronDown, ExternalLink, FileText } from 'lucide-react';
import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import { Link, useLocation } from 'react-router';
import remarkGfm from 'remark-gfm';
import type { Message } from '../../types/api';

export const MessageBubble = memo(function MessageBubble({
  message,
  streaming = false,
}: {
  message: Message;
  streaming?: boolean;
}) {
  const assistant = message.role === 'assistant';
  const location = useLocation();
  return (
    <article
      className={`flex motion-safe:animate-message-in ${assistant ? 'justify-start' : 'justify-end'}`}
      aria-label={`${message.role} message`}
    >
      <div
        className={`rounded-2xl px-4 py-3 text-sm leading-7 ${
          assistant
            ? 'max-w-[95%] border bg-white text-ink-800 dark:bg-ink-900 dark:text-ink-100 sm:max-w-[88%]'
            : 'max-w-[92%] bg-ink-800 text-white ring-1 ring-transparent dark:bg-ink-800 dark:text-ink-100 dark:ring-white/[0.06] sm:max-w-[82%]'
        }`}
      >
        {assistant ? (
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
              {message.content || (streaming ? 'Thinking…' : '')}
            </ReactMarkdown>
            {streaming && message.content && (
              <span
                className="ml-1 inline-block h-4 w-1 animate-pulse bg-accent-600"
                aria-label="Answer streaming"
              />
            )}
          </div>
        ) : (
          <p className="whitespace-pre-wrap">{message.content}</p>
        )}

        {assistant && message.citations.length > 0 && (
          <details className="group mt-4 border-t pt-3">
            <summary className="flex cursor-pointer select-none items-center gap-1.5 rounded text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400 [&::-webkit-details-marker]:hidden">
              <ChevronDown
                className="size-3.5 shrink-0 transition-transform duration-150 group-open:rotate-180"
                aria-hidden="true"
              />
              Sources ({message.citations.length})
            </summary>
            <ul className="mt-3 space-y-2">
              {message.citations.map((citation) => (
                <li key={`${citation.document_id}-${citation.page_number}-${citation.ordinal}`}>
                  <Link
                    to={`/documents/${citation.document_id}/view?page=${citation.page_number}`}
                    state={{ returnTo: location.pathname }}
                    className="group/source block rounded-lg border bg-ink-50 p-3 transition-all duration-150 hover:-translate-y-px hover:border-accent-400 hover:shadow dark:bg-ink-950"
                    aria-label={`Open ${citation.document_name} page ${citation.page_number}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex min-w-0 items-center gap-2 font-semibold text-ink-800 dark:text-ink-100">
                        <FileText className="size-4 shrink-0 text-accent-700 dark:text-accent-400" />
                        <span className="truncate">{citation.document_name}</span>
                        <span className="shrink-0 text-ink-500 dark:text-ink-400">
                          p. {citation.page_number}
                        </span>
                      </span>
                      <ExternalLink className="size-3.5 shrink-0 text-ink-500 group-hover/source:text-accent-700 dark:text-ink-400 dark:group-hover/source:text-accent-400" />
                    </div>
                    <p className="mt-2 line-clamp-3 text-xs leading-5 text-ink-500 dark:text-ink-400">
                      {citation.excerpt}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </article>
  );
});
