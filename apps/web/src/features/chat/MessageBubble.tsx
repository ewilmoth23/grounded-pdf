import { ChevronDown, ExternalLink, FileText } from 'lucide-react';
import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import { Link, useLocation } from 'react-router';
import remarkGfm from 'remark-gfm';
import type { Message } from '../../types/api';
import { highlightParamValue } from '../../utils/highlight';
import { VerificationPanel } from './VerificationPanel';

/** Streamed or stopped placeholders are not persisted, so they cannot be verified. */
function isPersistedId(id: string): boolean {
  return id !== 'streaming' && !id.startsWith('stopped-');
}

interface CompareSection {
  title: string;
  body: string;
}

/** Split a compare answer into its per-document H2 sections; null below 2 sections. */
function parseCompareSections(content: string): CompareSection[] | null {
  const headings = [...content.matchAll(/^## +(.+)$/gm)];
  if (headings.length < 2) return null;
  return headings.map((heading, index) => {
    const start = (heading.index ?? 0) + heading[0].length;
    const end = index + 1 < headings.length ? headings[index + 1].index : content.length;
    return { title: heading[1].trim(), body: content.slice(start, end).trim() };
  });
}

export const MessageBubble = memo(function MessageBubble({
  message,
  streaming = false,
  conversationId,
}: {
  message: Message;
  streaming?: boolean;
  conversationId?: string;
}) {
  const assistant = message.role === 'assistant';
  const compareSections =
    assistant && message.mode === 'compare' ? parseCompareSections(message.content) : null;
  const location = useLocation();
  const verifiable =
    assistant &&
    !streaming &&
    Boolean(conversationId) &&
    Boolean(message.content) &&
    isPersistedId(message.id);
  return (
    <article
      className={`flex motion-safe:animate-message-in ${assistant ? 'justify-start' : 'justify-end'}`}
      aria-label={`${message.role} message`}
    >
      <div
        className={`rounded-2xl px-4 py-3 text-sm leading-7 ${
          assistant
            ? `border bg-white text-ink-800 dark:bg-ink-900 dark:text-ink-100 ${
                compareSections ? 'w-full max-w-full' : 'max-w-[95%] sm:max-w-[88%]'
              }`
            : 'max-w-[92%] bg-ink-800 text-white ring-1 ring-transparent dark:bg-ink-800 dark:text-ink-100 dark:ring-white/[0.06] sm:max-w-[82%]'
        }`}
      >
        {assistant && compareSections ? (
          <div className="grid gap-3 lg:grid-cols-2" data-testid="compare-sections">
            {compareSections.map((section) => (
              <section
                key={section.title}
                className="rounded-xl border bg-ink-50 p-3 dark:bg-ink-950"
                aria-label={`Answer from ${section.title}`}
              >
                <h3 className="mb-2 flex items-center gap-2 border-b pb-2 text-sm font-semibold text-ink-800 dark:text-ink-100">
                  <FileText
                    className="size-4 shrink-0 text-accent-700 dark:text-accent-400"
                    aria-hidden="true"
                  />
                  <span className="min-w-0 truncate">{section.title}</span>
                </h3>
                <div className="prose prose-sm max-w-none dark:prose-invert">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
                    {section.body}
                  </ReactMarkdown>
                </div>
              </section>
            ))}
            {streaming && (
              <span
                className="ml-1 inline-block h-4 w-1 animate-pulse bg-accent-600"
                aria-label="Answer streaming"
              />
            )}
          </div>
        ) : assistant ? (
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
                    to={`/documents/${citation.document_id}/view?page=${citation.page_number}&highlight=${encodeURIComponent(highlightParamValue(citation.excerpt))}`}
                    state={{ returnTo: location.pathname, highlight: citation.excerpt }}
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

        {verifiable && (
          <VerificationPanel conversationId={conversationId!} messageId={message.id} />
        )}
      </div>
    </article>
  );
});
