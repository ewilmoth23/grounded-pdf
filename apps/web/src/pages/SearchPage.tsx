import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ExternalLink, FileSearch, FileText, FileUp, Search } from 'lucide-react';
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router';
import { api } from '../api/client';
import { EmptyState, ErrorAlert } from '../components/Feedback';
import { Skeleton } from '../components/Skeleton';
import { DocumentPicker } from '../features/chat/DocumentPicker';
import type { SearchMatch } from '../types/api';
import { highlightParamValue } from '../utils/highlight';

/** Fewer characters return everything vaguely similar; wait for a real phrase. */
const MIN_QUERY_LENGTH = 3;
const DEBOUNCE_MS = 350;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Wrap occurrences of the query's meaningful terms in <mark>, client-side only. */
function emphasizeTerms(excerpt: string, query: string): ReactNode {
  const terms = [
    ...new Set((query.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter((t) => t.length > 2)),
  ];
  if (terms.length === 0) return excerpt;
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi');
  const parts = excerpt.split(pattern);
  return parts.map((part, index) =>
    index % 2 === 1 ? (
      <mark
        key={index}
        className="rounded-sm bg-accent-100 font-semibold text-accent-900 dark:bg-accent-950 dark:text-accent-200"
      >
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

function MatchStrength({ score }: { score: number }) {
  const percent = Math.round(Math.max(0, Math.min(1, score)) * 100);
  return (
    <span className="flex shrink-0 items-center gap-2">
      <span
        aria-hidden="true"
        className="h-1 w-14 overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800"
      >
        <span
          className="block h-full rounded-full bg-accent-600 dark:bg-accent-400"
          style={{ width: `${percent}%` }}
        />
      </span>
      <span className="text-xs tabular-nums text-ink-500 dark:text-ink-400">{percent}% match</span>
    </span>
  );
}

export function SearchPage() {
  const location = useLocation();
  const inputRef = useRef<HTMLInputElement>(null);
  const resultRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setDebouncedQuery('');
      return;
    }
    const timer = window.setTimeout(() => setDebouncedQuery(trimmed), DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  // ⌘K / Ctrl+K refocuses the query field when the page is already open
  // (AppLayout owns the navigation half of the shortcut).
  useEffect(() => {
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const documents = useQuery({ queryKey: ['documents'], queryFn: api.documents.list });
  const readyDocuments = documents.data?.filter((doc) => doc.status === 'ready') ?? [];
  const docKey = [...selectedIds].sort();
  const search = useQuery({
    queryKey: ['search', debouncedQuery, docKey],
    queryFn: () => api.search.query(debouncedQuery, selectedIds),
    enabled: debouncedQuery.length >= MIN_QUERY_LENGTH,
    placeholderData: keepPreviousData,
  });

  const matches = search.data?.matches ?? [];
  // An active document filter that matches nothing ready is not the same as
  // an empty library; do not show the upload prompt in that case.
  const filterMatchedNone = search.data?.documents_available === false && selectedIds.length > 0;
  const noReadyDocuments =
    !filterMatchedNone &&
    ((documents.isSuccess && readyDocuments.length === 0) ||
      search.data?.documents_available === false);

  function focusResult(index: number) {
    resultRefs.current[index]?.focus();
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' && matches.length > 0) {
      event.preventDefault();
      focusResult(0);
    }
  }

  function onResultKeyDown(event: KeyboardEvent<HTMLAnchorElement>, index: number) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      focusResult(Math.min(index + 1, matches.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (index === 0) inputRef.current?.focus();
      else focusResult(index - 1);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      inputRef.current?.focus();
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
      <div className="mb-7">
        <p className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-accent-700 dark:text-accent-400">
          Quote search
        </p>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Search</h1>
        <p className="mt-2 text-sm text-ink-500 dark:text-ink-400">
          Exact passages from your documents — no AI generation.
        </p>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1 basis-64">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-400 dark:text-ink-500"
            aria-hidden="true"
          />
          <input
            ref={inputRef}
            type="search"
            className="field pl-9"
            placeholder="Search for a phrase, fact, or quote"
            aria-label="Search your documents"
            value={query}
            autoFocus
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onInputKeyDown}
          />
        </div>
        {readyDocuments.length > 0 && (
          <DocumentPicker
            documents={documents.data ?? []}
            selected={selectedIds}
            onChange={setSelectedIds}
          />
        )}
      </div>

      {filterMatchedNone ? (
        <div className="panel">
          <EmptyState
            icon={FileSearch}
            title="None of the selected documents are ready to search."
            description="Widen the document filter or wait for the selected documents to finish processing."
          />
        </div>
      ) : noReadyDocuments ? (
        <div className="panel">
          <EmptyState
            icon={FileUp}
            title="No documents to search"
            description="Upload a PDF and wait for it to finish processing. Search only ever returns text stored from your own documents."
            action={
              <Link to="/documents" className="button-secondary">
                Go to Documents
              </Link>
            }
          />
        </div>
      ) : query.trim().length < MIN_QUERY_LENGTH ? (
        <p className="text-sm text-ink-500 dark:text-ink-400">
          Type at least {MIN_QUERY_LENGTH} characters. Results update as you type and never leave
          your machine.
        </p>
      ) : search.isError ? (
        <ErrorAlert message={search.error.message} />
      ) : search.isPending ? (
        <div className="space-y-3" aria-label="Searching your documents">
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index} className="panel space-y-2.5 p-4">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          ))}
        </div>
      ) : matches.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={FileSearch}
            title="No matching passages"
            description="Nothing similar enough was found in the selected documents. Try different wording or widen the document filter."
          />
        </div>
      ) : (
        <>
          <p role="status" className="mb-3 text-xs font-medium text-ink-600 dark:text-ink-300">
            {matches.length} {matches.length === 1 ? 'passage' : 'passages'} found · use ↑ ↓ to move
            and Enter to open
          </p>
          <ul className="space-y-3" aria-label="Search results">
            {matches.map((match: SearchMatch, index: number) => (
              <li key={`${match.document_id}-${match.page_number}-${index}`}>
                <Link
                  ref={(element) => {
                    resultRefs.current[index] = element;
                  }}
                  to={`/documents/${match.document_id}/view?page=${match.page_number}&highlight=${encodeURIComponent(highlightParamValue(match.excerpt))}`}
                  state={{ returnTo: location.pathname, highlight: match.excerpt }}
                  onKeyDown={(event) => onResultKeyDown(event, index)}
                  className="group/source block rounded-lg border bg-white p-4 transition-all duration-150 hover:-translate-y-px hover:border-accent-400 hover:shadow dark:bg-ink-900"
                  aria-label={`Open ${match.document_name} page ${match.page_number}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-2 text-sm font-semibold text-ink-800 dark:text-ink-100">
                      <FileText
                        className="size-4 shrink-0 text-accent-700 dark:text-accent-400"
                        aria-hidden="true"
                      />
                      <span className="truncate">{match.document_name}</span>
                      <span className="shrink-0 rounded-full bg-ink-100 px-2 py-0.5 text-xs font-medium text-ink-600 dark:bg-ink-800 dark:text-ink-300">
                        p. {match.page_number}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-3">
                      <MatchStrength score={match.score} />
                      <ExternalLink
                        className="size-3.5 shrink-0 text-ink-500 group-hover/source:text-accent-700 dark:text-ink-400 dark:group-hover/source:text-accent-400"
                        aria-hidden="true"
                      />
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-4 text-xs leading-5 text-ink-600 dark:text-ink-300">
                    {emphasizeTerms(match.excerpt, search.data?.query ?? debouncedQuery)}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
