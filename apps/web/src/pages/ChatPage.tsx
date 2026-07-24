import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, Columns2, MessageSquareText, PanelLeft, Square } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router';
import { api } from '../api/client';
import { streamQuestion } from '../api/stream';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorAlert, EmptyState } from '../components/Feedback';
import { Skeleton } from '../components/Skeleton';
import { ConversationNav } from '../features/chat/ConversationNav';
import { DocumentPicker } from '../features/chat/DocumentPicker';
import { MessageBubble } from '../features/chat/MessageBubble';
import { useModalBehavior } from '../hooks/useModalBehavior';
import type { Citation, Conversation, Message, QuestionMode } from '../types/api';

const DEFAULT_TITLE = 'New conversation';
const SUGGESTED_PROMPTS = [
  'Summarize the key findings',
  'What methodology was used?',
  'What are the stated limitations?',
];
const COMPARE_PROMPTS = [
  'Compare the methodologies',
  'Where do these documents disagree?',
  "Summarize each document's conclusions",
];

function deriveTitle(question: string, maxLength = 48): string {
  if (question.length <= maxLength) return question;
  const slice = question.slice(0, maxLength);
  const lastSpace = slice.lastIndexOf(' ');
  const cut = lastSpace > maxLength / 2 ? slice.slice(0, lastSpace) : slice;
  return `${cut.trimEnd()}…`;
}

export function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState('');
  const [mode, setMode] = useState<QuestionMode>('answer');
  const [streaming, setStreaming] = useState(false);
  const [streamMessages, setStreamMessages] = useState<Message[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);
  const [atBottom, setAtBottom] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const nearBottomRef = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  const tokenBufferRef = useRef('');
  const flushFrameRef = useRef<number | null>(null);

  const closeNav = useCallback(() => setNavOpen(false), []);
  useModalBehavior(navOpen, closeNav);

  const conversations = useQuery({ queryKey: ['conversations'], queryFn: api.conversations.list });
  const documents = useQuery({ queryKey: ['documents'], queryFn: api.documents.list });
  const detail = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => api.conversations.get(conversationId!),
    enabled: Boolean(conversationId),
  });

  useEffect(() => {
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setStreaming(false);
    setStreamMessages(null);
    setError(null);
  }, [conversationId]);
  useEffect(
    () => () => {
      streamAbortRef.current?.abort();
      streamAbortRef.current = null;
      if (flushFrameRef.current !== null) cancelAnimationFrame(flushFrameRef.current);
    },
    [],
  );

  const createConversation = useMutation({
    mutationFn: () => api.conversations.create(),
    onMutate: () => setError(null),
    onSuccess: async (conversation) => {
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
      void navigate(`/chat/${conversation.id}`);
    },
    onError: (mutationError: Error) => setError(mutationError.message),
  });
  const selectDocuments = useMutation({
    mutationFn: (ids: string[]) => api.conversations.selectDocuments(conversationId!, ids),
    onMutate: () => setError(null),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] });
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
    onError: (mutationError: Error) => setError(mutationError.message),
  });
  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      api.conversations.rename(id, title),
    onMutate: () => setError(null),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
      await queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] });
    },
    onError: (mutationError: Error) => setError(mutationError.message),
  });
  const remove = useMutation({
    mutationFn: api.conversations.delete,
    onMutate: () => setError(null),
    onSuccess: async (_, removedId) => {
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
      if (removedId === conversationId) void navigate('/chat');
    },
    onError: (mutationError: Error) => setError(mutationError.message),
  });

  const messages = useMemo(
    () => streamMessages ?? detail.data?.messages ?? [],
    [streamMessages, detail.data?.messages],
  );

  const selectedDocumentIds = detail.data?.document_ids;
  const readySelectedCount = useMemo(
    () =>
      (selectedDocumentIds ?? []).filter((id) =>
        documents.data?.some((doc) => doc.id === id && doc.status === 'ready'),
      ).length,
    [selectedDocumentIds, documents.data],
  );
  const compareAvailable = readySelectedCount >= 2;

  // Compare needs two ready documents; fall back when the selection shrinks.
  useEffect(() => {
    if (!compareAvailable) setMode('answer');
  }, [compareAvailable]);

  const updateScrollState = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    nearBottomRef.current = nearBottom;
    setAtBottom(nearBottom);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && nearBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  function jumpToLatest() {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    nearBottomRef.current = true;
    setAtBottom(true);
  }

  function resetComposerHeight() {
    const el = textareaRef.current;
    if (el) el.style.height = '';
  }

  function autoGrowComposer() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = '';
    el.style.height = `${el.scrollHeight}px`;
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const value = question.trim();
    if (!conversationId || !value || streaming) return;
    if (!detail.data?.document_ids.length) {
      setError('Select at least one processed document before asking a question.');
      return;
    }
    if (mode === 'compare' && !compareAvailable) {
      setError('Compare mode needs at least two ready documents selected.');
      return;
    }
    setQuestion('');
    resetComposerHeight();
    setError(null);
    setStreaming(true);
    setAnnouncement('Generating answer…');
    const controller = new AbortController();
    streamAbortRef.current = controller;
    const baseMessages = [...messages];
    let pendingCitations: Citation[] = [];
    tokenBufferRef.current = '';

    // Auto-title the conversation from its first question (fire-and-forget).
    if (baseMessages.length === 0 && detail.data.title === DEFAULT_TITLE) {
      void api.conversations
        .rename(conversationId, deriveTitle(value))
        .then(async () => {
          await queryClient.invalidateQueries({ queryKey: ['conversations'] });
          await queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] });
        })
        .catch(() => undefined);
    }

    const appendChunk = (chunk: string) => {
      if (!chunk) return;
      setStreamMessages((current) => {
        const next = current ? [...current] : [...baseMessages];
        const last = next.at(-1);
        if (last?.id === 'streaming')
          next[next.length - 1] = {
            ...last,
            content: last.content + chunk,
            citations: pendingCitations,
          };
        return next;
      });
    };
    const flushTokens = () => {
      flushFrameRef.current = null;
      const chunk = tokenBufferRef.current;
      tokenBufferRef.current = '';
      appendChunk(chunk);
    };
    const finalizeBuffer = () => {
      if (flushFrameRef.current !== null) {
        cancelAnimationFrame(flushFrameRef.current);
        flushFrameRef.current = null;
      }
      const chunk = tokenBufferRef.current;
      tokenBufferRef.current = '';
      appendChunk(chunk);
    };

    try {
      await streamQuestion(
        conversationId,
        value,
        {
          onMetadata: ({ user_message, citations }) => {
            pendingCitations = citations;
            setStreamMessages([
              ...baseMessages,
              user_message,
              {
                id: 'streaming',
                role: 'assistant',
                content: '',
                mode: mode === 'compare' ? 'compare' : null,
                citations,
                created_at: new Date().toISOString(),
              },
            ]);
          },
          onToken: (token) => {
            tokenBufferRef.current += token;
            if (flushFrameRef.current === null)
              flushFrameRef.current = requestAnimationFrame(flushTokens);
          },
          onDone: (message) => {
            finalizeBuffer();
            setStreamMessages((current) => {
              if (!current) return [...baseMessages, message];
              const last = current.at(-1);
              if (last?.id !== 'streaming') return [...current, message];
              return [...current.slice(0, -1), message];
            });
          },
        },
        controller.signal,
        mode,
      );
      await queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] });
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
      // Server state owns the transcript again.
      setStreamMessages(null);
    } catch (streamError) {
      finalizeBuffer();
      if (controller.signal.aborted) {
        // User-initiated stop: keep any partial answer, no error banner.
        setStreamMessages(
          (current) =>
            current?.map((message) =>
              message.id === 'streaming' ? { ...message, id: `stopped-${Date.now()}` } : message,
            ) ?? null,
        );
      } else {
        setError(
          streamError instanceof Error ? streamError.message : 'The answer stream was interrupted.',
        );
        setStreamMessages(
          (current) => current?.filter((message) => message.id !== 'streaming') ?? null,
        );
        // Give the failed question back to the composer unless the user moved on.
        setQuestion((current) => (current.trim() ? current : value));
      }
    } finally {
      if (streamAbortRef.current === controller) {
        streamAbortRef.current = null;
        setStreaming(false);
        setAnnouncement(controller.signal.aborted ? 'Generation stopped' : 'Answer complete');
      }
    }
  }

  function stopStreaming() {
    streamAbortRef.current?.abort();
  }

  function requestRename(conversation: Conversation, title: string) {
    if (streaming || rename.isPending || remove.isPending) return;
    rename.mutate({ id: conversation.id, title });
  }

  function requestDelete(conversation: Conversation) {
    if (streaming || rename.isPending || remove.isPending) return;
    setPendingDelete(conversation);
  }

  function fillPrompt(prompt: string) {
    setQuestion(prompt);
    textareaRef.current?.focus();
  }

  const nav = (
    <ConversationNav
      conversations={conversations.data ?? []}
      activeId={conversationId}
      onCreate={() => createConversation.mutate()}
      onRename={requestRename}
      onDelete={requestDelete}
      busy={createConversation.isPending || rename.isPending || remove.isPending || streaming}
    />
  );

  const hasSelectedDocuments = Boolean(detail.data?.document_ids.length);

  return (
    <div className="h-[calc(100dvh-3.5rem)] lg:h-dvh md:grid md:grid-cols-[250px_minmax(0,1fr)]">
      <div className="hidden min-h-0 md:block">{nav}</div>
      {navOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-black/40"
            aria-hidden="true"
            onClick={() => setNavOpen(false)}
          />
          <div
            className="relative h-full w-72 motion-safe:transition-transform"
            role="dialog"
            aria-modal="true"
            aria-label="Conversations"
            onClick={(event) => {
              // Close only when an actual conversation link is followed.
              if ((event.target as HTMLElement).closest('a')) setNavOpen(false);
            }}
          >
            {nav}
          </div>
        </div>
      )}
      <section className="flex min-h-0 flex-col">
        <header className="flex min-h-16 items-center justify-between gap-3 border-b bg-white px-4 dark:bg-ink-900 sm:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <button
              className="button-ghost px-2 md:hidden"
              onClick={() => setNavOpen(true)}
              aria-label="Open conversations"
            >
              <PanelLeft className="size-5" />
            </button>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold sm:text-base">
                {detail.data?.title ?? 'Research chat'}
              </h1>
              <p className="hidden text-xs text-ink-500 dark:text-ink-400 sm:block">
                Answers use only your selected documents
              </p>
            </div>
          </div>
          {conversationId && (
            <DocumentPicker
              documents={documents.data ?? []}
              selected={detail.data?.document_ids ?? []}
              onChange={(ids) => selectDocuments.mutate(ids)}
              disabled={streaming}
            />
          )}
        </header>

        {error && (
          <div className="border-b bg-white px-4 py-3 dark:bg-ink-900 sm:px-6">
            <ErrorAlert message={error} />
          </div>
        )}
        {detail.isError && detail.data && (
          <div className="border-b bg-white px-4 py-3 dark:bg-ink-900 sm:px-6">
            <ErrorAlert message={`The conversation could not refresh: ${detail.error.message}`} />
          </div>
        )}

        <div className="sr-only" role="status" aria-live="polite">
          {announcement}
        </div>

        {!conversationId ? (
          <div className="flex-1 overflow-auto">
            <EmptyState
              icon={MessageSquareText}
              title="Start a grounded conversation"
              description="Create a conversation, select one or more processed documents, then ask a question. Every supported answer includes page-level sources."
              action={
                <button
                  className="button-primary"
                  onClick={() => createConversation.mutate()}
                  disabled={createConversation.isPending}
                >
                  <MessageSquareText className="size-4" /> New conversation
                </button>
              }
            />
          </div>
        ) : detail.isLoading ? (
          <div
            className="flex-1 space-y-5 bg-ink-50 p-6 dark:bg-ink-950"
            aria-label="Loading conversation"
          >
            <Skeleton className="ml-auto h-14 w-2/3 rounded-2xl" />
            <Skeleton className="h-28 w-4/5 rounded-2xl" />
            <Skeleton className="ml-auto h-14 w-1/2 rounded-2xl" />
          </div>
        ) : detail.isError && !detail.data ? (
          <div className="p-6">
            <ErrorAlert message={detail.error.message} />
          </div>
        ) : (
          <>
            <div className="relative min-h-0 flex-1">
              <div
                ref={scrollRef}
                onScroll={updateScrollState}
                className="h-full overflow-y-auto bg-ink-50 dark:bg-ink-950"
              >
                <div className="mx-auto max-w-4xl space-y-5 px-4 py-6 sm:px-6 sm:py-8">
                  {messages.length === 0 ? (
                    <>
                      <EmptyState
                        icon={MessageSquareText}
                        title={
                          hasSelectedDocuments
                            ? 'Ask about your documents'
                            : 'Choose source documents'
                        }
                        description={
                          hasSelectedDocuments
                            ? 'Try a specific question. GroundedPDF will return an evidence-based answer or tell you when the evidence is insufficient.'
                            : 'Use the document selector above to choose one or more processed PDFs for this conversation.'
                        }
                      />
                      {hasSelectedDocuments && (
                        <div className="flex flex-wrap justify-center gap-2">
                          {(mode === 'compare' ? COMPARE_PROMPTS : SUGGESTED_PROMPTS).map(
                            (prompt) => (
                              <button
                                key={prompt}
                                type="button"
                                className="rounded-full border bg-white px-4 py-2 text-sm text-ink-600 transition-all duration-150 hover:-translate-y-px hover:border-accent-400 hover:text-ink-950 hover:shadow dark:bg-ink-900 dark:text-ink-300 dark:hover:text-white"
                                onClick={() => fillPrompt(prompt)}
                              >
                                {prompt}
                              </button>
                            ),
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    messages.map((message) => (
                      <MessageBubble
                        key={message.id}
                        message={message}
                        streaming={streaming && message.id === 'streaming'}
                        conversationId={conversationId}
                      />
                    ))
                  )}
                </div>
              </div>
              {!atBottom && messages.length > 0 && (
                <button
                  type="button"
                  className="button-primary absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full px-4 shadow-lg"
                  onClick={jumpToLatest}
                >
                  <ArrowDown className="size-4" /> Jump to latest
                </button>
              )}
            </div>
            <div className="border-t bg-white p-3 dark:bg-ink-900 sm:p-4">
              <div className="mx-auto max-w-4xl">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <div
                    role="group"
                    aria-label="Question mode"
                    className="inline-flex rounded-lg border bg-ink-50 p-0.5 dark:bg-ink-950"
                  >
                    <button
                      type="button"
                      className={`inline-flex min-h-8 items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition-colors duration-150 ${
                        mode === 'answer'
                          ? 'bg-white text-ink-950 shadow-sm dark:bg-ink-800 dark:text-white'
                          : 'text-ink-600 hover:text-ink-950 dark:text-ink-300 dark:hover:text-white'
                      }`}
                      aria-pressed={mode === 'answer'}
                      onClick={() => setMode('answer')}
                      disabled={streaming}
                    >
                      <MessageSquareText className="size-4" aria-hidden="true" /> Answer
                    </button>
                    <button
                      type="button"
                      className={`inline-flex min-h-8 items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${
                        mode === 'compare'
                          ? 'bg-white text-ink-950 shadow-sm dark:bg-ink-800 dark:text-white'
                          : 'text-ink-600 hover:text-ink-950 dark:text-ink-300 dark:hover:text-white'
                      }`}
                      aria-pressed={mode === 'compare'}
                      onClick={() => setMode('compare')}
                      disabled={streaming || !compareAvailable}
                      title={
                        compareAvailable
                          ? undefined
                          : 'Select at least two ready documents to compare.'
                      }
                    >
                      <Columns2 className="size-4" aria-hidden="true" /> Compare docs
                    </button>
                  </div>
                  {mode === 'compare' && (
                    <p className="text-xs text-ink-500 dark:text-ink-400">
                      One answer per document, each grounded only in that document.
                    </p>
                  )}
                </div>
                <form onSubmit={(event) => void send(event)} className="relative">
                  <label htmlFor="question" className="sr-only">
                    Ask a question
                  </label>
                  <textarea
                    id="question"
                    ref={textareaRef}
                    className="field max-h-48 min-h-14 resize-none py-3 pl-4 pr-14"
                    value={question}
                    onChange={(event) => {
                      setQuestion(event.target.value);
                      autoGrowComposer();
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                    placeholder={
                      mode === 'compare'
                        ? 'Ask one question to answer from each selected document…'
                        : 'Ask a question about the selected documents…'
                    }
                    maxLength={4000}
                    rows={2}
                  />
                  {streaming ? (
                    <button
                      className="button-secondary absolute bottom-2 right-2 size-10 px-0"
                      type="button"
                      onClick={stopStreaming}
                      aria-label="Stop generating"
                    >
                      <Square className="size-4 fill-current" />
                    </button>
                  ) : (
                    <button
                      className="button-primary absolute bottom-2 right-2 size-10 px-0"
                      type="submit"
                      disabled={!question.trim()}
                      aria-label="Send question"
                    >
                      <ArrowUp className="size-4" />
                    </button>
                  )}
                </form>
                <div className="mt-2 flex items-center justify-center gap-3">
                  <p className="text-center text-xs text-ink-500 dark:text-ink-400">
                    Verify important claims against the cited page. Shift+Enter adds a line.
                  </p>
                  {question.length > 3600 && (
                    <p className="shrink-0 text-xs tabular-nums text-ink-500 dark:text-ink-400">
                      {question.length}/4000
                    </p>
                  )}
                </div>
              </div>
            </div>
          </>
        )}
      </section>
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete conversation"
        description={
          <>
            <strong className="font-semibold text-ink-800 dark:text-ink-100">
              {pendingDelete?.title}
            </strong>{' '}
            and all of its messages will be permanently deleted.
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
