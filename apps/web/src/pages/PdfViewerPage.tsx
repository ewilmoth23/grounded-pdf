import { ArrowLeft, ChevronLeft, ChevronRight, Download, ZoomIn, ZoomOut } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { Link, useLocation, useParams, useSearchParams } from 'react-router';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { api } from '../api/client';
import { ErrorAlert } from '../components/Feedback';
import { Skeleton } from '../components/Skeleton';

const pdfWorkerUrl = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url);
pdfWorkerUrl.searchParams.set('v', pdfjs.version);
pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl.toString();

export function PdfViewerPage() {
  const { documentId } = useParams();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const parsedPage = Number.parseInt(searchParams.get('page') ?? '1', 10);
  const requestedPage = Number.isSafeInteger(parsedPage) ? Math.max(1, parsedPage) : 1;
  const requestedReturnTo = (location.state as { returnTo?: unknown } | null)?.returnTo;
  const returnTo =
    typeof requestedReturnTo === 'string' && requestedReturnTo.startsWith('/chat')
      ? requestedReturnTo
      : '/chat';
  const [pages, setPages] = useState<number | null>(null);
  const [scale, setScale] = useState(1.15);
  const [error, setError] = useState<string | null>(null);
  const [pageInput, setPageInput] = useState(String(requestedPage));

  useEffect(() => setError(null), [documentId]);
  useEffect(() => setPageInput(String(requestedPage)), [requestedPage]);

  const navigatePage = useCallback(
    (page: number) => {
      setSearchParams(
        (current) => {
          const bounded = Math.max(1, Math.min(pages ?? page, page));
          const next = new URLSearchParams(current);
          next.set('page', String(bounded));
          return next;
        },
        { replace: true },
      );
    },
    [pages, setSearchParams],
  );

  const commitPageInput = useCallback(() => {
    const parsed = Number.parseInt(pageInput, 10);
    if (Number.isSafeInteger(parsed) && parsed >= 1) {
      navigatePage(parsed);
    } else {
      setPageInput(String(requestedPage));
    }
  }, [navigatePage, pageInput, requestedPage]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target instanceof HTMLInputElement ||
          target instanceof HTMLTextAreaElement ||
          target instanceof HTMLSelectElement ||
          target.isContentEditable)
      )
        return;
      if (event.key === 'ArrowLeft') navigatePage(requestedPage - 1);
      else if (event.key === 'ArrowRight') navigatePage(requestedPage + 1);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [navigatePage, requestedPage]);

  if (!documentId)
    return (
      <div className="p-6">
        <ErrorAlert message="Document identifier is missing." />
      </div>
    );
  const fileUrl = api.documents.fileUrl(documentId);

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col bg-ink-100 dark:bg-ink-950 lg:h-dvh">
      <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b bg-white px-4 dark:bg-ink-900 sm:px-6">
        <div className="flex items-center gap-3">
          <Link to={returnTo} className="button-ghost px-2" aria-label="Back to chat">
            <ArrowLeft className="size-5" />
          </Link>
          <div>
            <h1 className="text-sm font-semibold sm:text-base">Source document</h1>
            <p className="text-xs text-accent-700 dark:text-accent-400">
              Cited page {requestedPage}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            className="button-ghost px-2"
            onClick={() => setScale((value) => Math.max(0.65, value - 0.15))}
            aria-label="Zoom out"
          >
            <ZoomOut className="size-4" />
          </button>
          <span className="w-12 text-center text-xs text-ink-500 dark:text-ink-400">
            {Math.round(scale * 100)}%
          </span>
          <button
            className="button-ghost px-2"
            onClick={() => setScale((value) => Math.min(2.2, value + 0.15))}
            aria-label="Zoom in"
          >
            <ZoomIn className="size-4" />
          </button>
          <a href={fileUrl} download className="button-ghost ml-1 px-2" aria-label="Download PDF">
            <Download className="size-4" />
          </a>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center justify-center gap-3 border-b bg-white px-4 py-2 dark:bg-ink-900">
          <button
            className="button-ghost px-2"
            onClick={() => navigatePage(requestedPage - 1)}
            disabled={requestedPage <= 1}
            aria-label="Previous page"
          >
            <ChevronLeft className="size-4" />
          </button>
          <label className="flex items-center gap-2 text-xs text-ink-500 dark:text-ink-400">
            Page
            <input
              className="field w-16 py-1.5 text-center"
              type="number"
              min={1}
              max={pages ?? undefined}
              value={pageInput}
              onChange={(event) => setPageInput(event.target.value)}
              onBlur={commitPageInput}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  commitPageInput();
                }
              }}
              aria-label="Page number"
            />
            of {pages ?? '…'}
          </label>
          <button
            className="button-ghost px-2"
            onClick={() => navigatePage(requestedPage + 1)}
            disabled={pages !== null && requestedPage >= pages}
            aria-label="Next page"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-8">
          {error && (
            <div className="mx-auto mb-4 max-w-xl">
              <ErrorAlert message={error} />
            </div>
          )}
          <Document
            file={fileUrl}
            onLoadSuccess={({ numPages }) => {
              setPages(numPages);
              if (requestedPage > numPages) navigatePage(numPages);
            }}
            onLoadError={() =>
              setError(
                'The PDF could not be displayed. It may have been deleted or become unavailable.',
              )
            }
            loading={
              <Skeleton className="mx-auto h-[70vh] max-w-3xl rounded" label="Loading PDF" />
            }
          >
            <div
              className="mx-auto w-fit rounded-md border-4 border-accent-500 bg-white shadow-2xl"
              aria-label={`Cited page ${requestedPage}`}
            >
              <Page
                pageNumber={requestedPage}
                scale={scale}
                renderTextLayer
                renderAnnotationLayer
              />
            </div>
          </Document>
        </div>
      </div>
    </div>
  );
}
