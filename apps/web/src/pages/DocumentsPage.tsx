import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText, FileUp, History, RefreshCw, RotateCcw, Trash2, UploadCloud } from 'lucide-react';
import { useRef, useState, type DragEvent } from 'react';
import { api } from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EmptyState, ErrorAlert } from '../components/Feedback';
import { Skeleton } from '../components/Skeleton';
import { StatusBadge } from '../components/StatusBadge';
import { formatBytes, formatDate } from '../utils/format';
import type { DocumentRecord } from '../types/api';

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [rejections, setRejections] = useState<string[]>([]);
  const [pendingDelete, setPendingDelete] = useState<DocumentRecord | null>(null);
  const documents = useQuery({
    queryKey: ['documents'],
    queryFn: api.documents.list,
    refetchInterval: (query) =>
      query.state.data?.some((doc) => ['queued', 'processing'].includes(doc.status)) ? 1500 : false,
  });

  const upload = useMutation({
    mutationFn: api.documents.upload,
    onMutate: () => {
      setUploadError(null);
      setRejections([]);
    },
    onSuccess: async (result) => {
      setRejections(result.rejected.map((item) => `${item.filename}: ${item.message}`));
      await queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
    onError: (error: Error) => setUploadError(error.message),
  });

  const retry = useMutation({
    mutationFn: api.documents.retry,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
  });
  const remove = useMutation({
    mutationFn: api.documents.delete,
    onSettled: async () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
  });
  const reprocessStale = useMutation({
    mutationFn: api.documents.reprocessStale,
    onSettled: async () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
  });
  const actionError = retry.error ?? remove.error ?? reprocessStale.error;
  const staleCount = documents.data?.filter((doc) => doc.stale_index).length ?? 0;

  function selectFiles(files: FileList | null) {
    if (!upload.isPending && files?.length) upload.mutate(Array.from(files));
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (upload.isPending) return;
    selectFiles(event.dataTransfer.files);
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-accent-700 dark:text-accent-400">
            Library
          </p>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Documents</h1>
          <p className="mt-2 text-sm text-ink-500 dark:text-ink-400">
            Upload PDFs to create a private, searchable research library.
          </p>
        </div>
        <button
          className="button-secondary"
          onClick={() => void documents.refetch()}
          disabled={documents.isFetching}
        >
          <RefreshCw className={`size-4 ${documents.isFetching ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      <div
        className={`mb-6 flex min-h-40 flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition-colors ${
          upload.isPending ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'
        } ${
          dragging
            ? 'border-accent-500 bg-accent-50 dark:bg-accent-950'
            : 'border-ink-300 bg-white hover:border-accent-400 dark:border-ink-700 dark:bg-ink-900'
        }`}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!upload.isPending) setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        onClick={() => {
          if (!upload.isPending) inputRef.current?.click();
        }}
        role="button"
        aria-disabled={upload.isPending}
        tabIndex={upload.isPending ? -1 : 0}
        onKeyDown={(event) => {
          if (!upload.isPending && (event.key === 'Enter' || event.key === ' '))
            inputRef.current?.click();
        }}
      >
        <UploadCloud
          className="mb-3 size-7 text-accent-700 dark:text-accent-400"
          aria-hidden="true"
        />
        <p className="font-semibold">
          {upload.isPending ? 'Uploading and validating…' : 'Drop PDF files here'}
        </p>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          or choose files · multiple PDFs supported
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          disabled={upload.isPending}
          className="sr-only"
          onClick={(event) => event.stopPropagation()}
          onChange={(event) => {
            selectFiles(event.target.files);
            event.currentTarget.value = '';
          }}
        />
      </div>

      {uploadError && (
        <div className="mb-4">
          <ErrorAlert message={uploadError} />
        </div>
      )}
      {rejections.length > 0 && (
        <div className="mb-4">
          <ErrorAlert message={rejections.join(' · ')} />
        </div>
      )}
      {actionError && (
        <div className="mb-4">
          <ErrorAlert message={actionError.message} />
        </div>
      )}
      {staleCount > 0 && (
        <div
          role="status"
          className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-800 dark:bg-amber-950"
        >
          <p className="text-sm text-amber-900 dark:text-amber-100">
            {staleCount === 1
              ? '1 document was indexed with different settings.'
              : `${staleCount} documents were indexed with different settings.`}{' '}
            Reprocess to keep retrieval accurate.
          </p>
          <button
            className="button-primary px-3 py-1.5 text-sm"
            disabled={reprocessStale.isPending}
            onClick={() => {
              if (!reprocessStale.isPending) reprocessStale.mutate();
            }}
          >
            {reprocessStale.isPending
              ? 'Queueing…'
              : `Reprocess ${staleCount} ${staleCount === 1 ? 'document' : 'documents'}`}
          </button>
        </div>
      )}

      {documents.isError ? (
        <ErrorAlert message={documents.error.message} />
      ) : documents.isLoading ? (
        <div className="panel overflow-hidden" aria-label="Loading documents">
          <ul className="divide-y">
            {Array.from({ length: 4 }, (_, index) => (
              <li key={index} className="p-4 sm:p-5">
                <div className="flex items-start gap-3 sm:gap-4">
                  <Skeleton className="hidden size-10 sm:block" />
                  <div className="min-w-0 flex-1 space-y-2.5">
                    <Skeleton className="h-4 w-1/3" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                  <Skeleton className="h-6 w-20 rounded-full" />
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : documents.data?.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={FileUp}
            title="No documents yet"
            description="Upload a PDF above. Text is extracted and embedded locally before it becomes available in chat."
          />
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <ul className="divide-y" aria-label="Uploaded documents">
            {documents.data?.map((doc) => (
              <li
                key={doc.id}
                className="p-4 transition-colors duration-150 hover:bg-ink-50/60 dark:hover:bg-ink-800/40 sm:p-5"
              >
                <div className="flex items-start gap-3 sm:gap-4">
                  <span className="mt-0.5 hidden rounded-lg bg-ink-100 p-2.5 text-ink-500 dark:bg-ink-800 dark:text-ink-300 sm:block">
                    <FileText className="size-5" aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="truncate font-semibold" title={doc.original_name}>
                        {doc.title ?? doc.original_name}
                      </h2>
                      <StatusBadge status={doc.status} />
                      {doc.stale_index && (
                        <span
                          className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-950 dark:text-amber-200"
                          title="This document's index was built with different settings."
                        >
                          <History className="size-3.5" aria-hidden="true" />
                          Index outdated
                        </span>
                      )}
                    </div>
                    {doc.title && (
                      <p className="mt-0.5 truncate text-xs text-ink-500 dark:text-ink-400">
                        {doc.original_name}
                      </p>
                    )}
                    <p className="mt-2 text-xs text-ink-500 dark:text-ink-400">
                      {formatBytes(doc.file_size)} · {doc.page_count || '—'} pages · uploaded{' '}
                      {formatDate(doc.created_at)}
                    </p>
                    {doc.status === 'processing' && (
                      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-ink-100 dark:bg-ink-800">
                        <div className="h-full w-1/3 rounded-full bg-accent-600 motion-safe:animate-indeterminate" />
                      </div>
                    )}
                    {doc.status === 'ready' && doc.searchable_page_count < doc.page_count && (
                      <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">
                        {doc.page_count - doc.searchable_page_count}{' '}
                        {doc.page_count - doc.searchable_page_count === 1
                          ? 'page has'
                          : 'pages have'}{' '}
                        no searchable text and may be scanned.
                      </p>
                    )}
                    {doc.status === 'deleted' && !doc.processing_error && (
                      <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">
                        Deletion was interrupted. Retry deletion to finish cleanup.
                      </p>
                    )}
                    {doc.processing_error && (
                      <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-300">
                        {doc.processing_error}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {doc.status === 'failed' && (
                      <button
                        className="button-ghost px-2"
                        disabled={retry.isPending || remove.isPending}
                        onClick={() => {
                          if (!retry.isPending && !remove.isPending) retry.mutate(doc.id);
                        }}
                        aria-label={`Retry ${doc.original_name}`}
                        title="Retry processing"
                      >
                        <RotateCcw className="size-4" />
                      </button>
                    )}
                    <button
                      className="button-ghost px-2 hover:text-red-700 dark:hover:text-red-300"
                      disabled={
                        ['queued', 'processing'].includes(doc.status) ||
                        retry.isPending ||
                        remove.isPending
                      }
                      onClick={() => {
                        if (retry.isPending || remove.isPending) return;
                        setPendingDelete(doc);
                      }}
                      aria-label={`${doc.status === 'deleted' ? 'Retry deletion of' : 'Delete'} ${doc.original_name}`}
                      title={
                        ['queued', 'processing'].includes(doc.status)
                          ? 'Wait for processing to finish before deleting'
                          : doc.status === 'deleted'
                            ? 'Retry deletion'
                            : 'Delete document'
                      }
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete document"
        description={
          <>
            <strong className="font-semibold text-ink-800 dark:text-ink-100">
              {pendingDelete?.original_name}
            </strong>{' '}
            and all of its indexed data will be permanently deleted.
          </>
        }
        confirmLabel="Delete"
        danger
        busy={remove.isPending}
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete.id);
          setPendingDelete(null);
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
