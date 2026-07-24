import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Server, SlidersHorizontal } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { api } from '../api/client';
import { ErrorAlert } from '../components/Feedback';
import { Skeleton } from '../components/Skeleton';
import { useTheme, type Theme } from '../hooks/useTheme';
import type { SafeSettings } from '../types/api';

type EditableSettings = Pick<
  SafeSettings,
  | 'model_provider'
  | 'model_name'
  | 'chunk_size'
  | 'chunk_overlap'
  | 'retrieval_count'
  | 'temperature'
  | 'max_output_tokens'
>;

function editableSettings(settings: SafeSettings): EditableSettings {
  const {
    model_provider,
    model_name,
    chunk_size,
    chunk_overlap,
    retrieval_count,
    temperature,
    max_output_tokens,
  } = settings;
  return {
    model_provider,
    model_name,
    chunk_size,
    chunk_overlap,
    retrieval_count,
    temperature,
    max_output_tokens,
  };
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings.get });
  const { theme, setTheme } = useTheme();
  const [form, setForm] = useState<EditableSettings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const serverSettings = settings.data;
  useEffect(() => {
    if (settings.data && !dirty) setForm(editableSettings(settings.data));
  }, [dirty, settings.data]);

  const update = useMutation({
    mutationFn: (values: EditableSettings) => api.settings.update(values),
    onSuccess: async (updated) => {
      queryClient.setQueryData(['settings'], updated);
      setForm(editableSettings(updated));
      setDirty(false);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
      await queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    if (form.chunk_overlap >= form.chunk_size) return;
    update.mutate(form);
  }

  const setNumber = (key: keyof EditableSettings, value: string) => {
    if (!form) return;
    setDirty(true);
    setForm({ ...form, [key]: Number(value) });
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 lg:px-8 lg:py-10">
      <div className="mb-7">
        <p className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-accent-700 dark:text-accent-400">
          Configuration
        </p>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Settings</h1>
        <p className="mt-2 text-sm text-ink-500 dark:text-ink-400">
          Model and retrieval preferences. Secrets remain server-side.
        </p>
      </div>

      {settings.isError && <ErrorAlert message={settings.error.message} />}
      {update.isError && (
        <div className="mb-4">
          <ErrorAlert message={update.error.message} />
        </div>
      )}
      {settings.isLoading || !form || !serverSettings ? (
        <div className="space-y-6" aria-label="Loading settings">
          {[0, 1].map((section) => (
            <div key={section} className="panel space-y-5 p-5 sm:p-6">
              <div className="flex items-start gap-3">
                <Skeleton className="size-9" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-64" />
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {[0, 1, 2, 3].map((field) => (
                  <div key={field} className="space-y-1.5">
                    <Skeleton className="h-3.5 w-24" />
                    <Skeleton className="h-10 w-full" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <form onSubmit={(event) => void submit(event)} className="space-y-6">
          <section className="panel p-5 sm:p-6">
            <div className="mb-5 flex items-start gap-3">
              <Server className="mt-0.5 size-5 text-accent-700 dark:text-accent-400" />
              <div>
                <h2 className="font-semibold">Model provider</h2>
                <p className="mt-1 text-sm text-ink-500 dark:text-ink-300">
                  Used to generate answers from retrieved source text.
                </p>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-medium">
                Provider
                <select
                  className="field mt-1.5"
                  value={form.model_provider}
                  onChange={(event) => {
                    setDirty(true);
                    setForm({
                      ...form,
                      model_provider: event.target.value as EditableSettings['model_provider'],
                    });
                  }}
                >
                  <option value="ollama">Ollama (local)</option>
                  <option value="openai_compatible">OpenAI-compatible endpoint</option>
                  {serverSettings.environment === 'test' && (
                    <option value="mock">Mock (testing)</option>
                  )}
                </select>
              </label>
              <label className="text-sm font-medium">
                Chat model
                <input
                  className="field mt-1.5"
                  value={form.model_name}
                  onChange={(event) => {
                    setDirty(true);
                    setForm({ ...form, model_name: event.target.value });
                  }}
                  required
                  maxLength={200}
                />
              </label>
              <label className="text-sm font-medium">
                Temperature
                <input
                  className="field mt-1.5"
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={form.temperature}
                  onChange={(event) => setNumber('temperature', event.target.value)}
                />
              </label>
              <label className="text-sm font-medium">
                Maximum output tokens
                <input
                  className="field mt-1.5"
                  type="number"
                  min="32"
                  max="32000"
                  value={form.max_output_tokens}
                  onChange={(event) => setNumber('max_output_tokens', event.target.value)}
                />
              </label>
            </div>
          </section>

          <section className="panel p-5 sm:p-6">
            <div className="mb-5 flex items-start gap-3">
              <SlidersHorizontal className="mt-0.5 size-5 text-accent-700 dark:text-accent-400" />
              <div>
                <h2 className="font-semibold">Retrieval</h2>
                <p className="mt-1 text-sm text-ink-500 dark:text-ink-300">
                  Changes apply to future processing and searches.
                </p>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="text-sm font-medium">
                Chunk size
                <input
                  className="field mt-1.5"
                  type="number"
                  min="200"
                  max="4000"
                  value={form.chunk_size}
                  onChange={(event) => setNumber('chunk_size', event.target.value)}
                />
              </label>
              <label className="text-sm font-medium">
                Chunk overlap
                <input
                  className="field mt-1.5"
                  type="number"
                  min="0"
                  max="1000"
                  value={form.chunk_overlap}
                  onChange={(event) => setNumber('chunk_overlap', event.target.value)}
                  aria-invalid={form.chunk_overlap >= form.chunk_size}
                />
              </label>
              <label className="text-sm font-medium">
                Retrieved chunks
                <input
                  className="field mt-1.5"
                  type="number"
                  min="1"
                  max="20"
                  value={form.retrieval_count}
                  onChange={(event) => setNumber('retrieval_count', event.target.value)}
                />
              </label>
            </div>
            {form.chunk_overlap >= form.chunk_size && (
              <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-300">
                Chunk overlap must be smaller than chunk size.
              </p>
            )}
            <p className="mt-3 text-sm text-ink-500 dark:text-ink-400">
              Changing chunk settings requires reprocessing existing documents — the Documents page
              will offer a one-click reprocess.
            </p>
            <dl className="mt-5 grid gap-3 border-t pt-5 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-ink-500 dark:text-ink-300">Embedding model</dt>
                <dd className="mt-1 break-all font-medium">{serverSettings.embedding_model}</dd>
              </div>
              <div>
                <dt className="text-ink-500 dark:text-ink-300">Maximum upload</dt>
                <dd className="mt-1 font-medium">
                  {serverSettings.max_upload_mb} MB per file · {serverSettings.max_upload_batch_mb}{' '}
                  MB per batch · {serverSettings.max_upload_files} files
                </dd>
              </div>
              <div>
                <dt className="text-ink-500 dark:text-ink-300">Optional OCR</dt>
                <dd className="mt-1 font-medium">
                  {serverSettings.ocr_enabled ? 'Enabled' : 'Disabled'}
                </dd>
              </div>
              <div>
                <dt className="text-ink-500 dark:text-ink-300">Environment</dt>
                <dd className="mt-1 font-medium capitalize">{serverSettings.environment}</dd>
              </div>
            </dl>
          </section>

          <section className="panel p-5 sm:p-6">
            <h2 className="font-semibold">Appearance</h2>
            <p className="mt-1 text-sm text-ink-500 dark:text-ink-300">
              Stored only in this browser.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {(['light', 'dark', 'system'] as Theme[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  className={
                    theme === option ? 'button-primary capitalize' : 'button-secondary capitalize'
                  }
                  onClick={() => setTheme(option)}
                >
                  {option.charAt(0).toUpperCase() + option.slice(1)}
                </button>
              ))}
            </div>
          </section>

          <div className="flex items-center justify-end gap-3">
            {saved && (
              <span
                className="flex items-center gap-1.5 text-sm text-accent-700 dark:text-accent-300"
                role="status"
                aria-live="polite"
              >
                <CheckCircle2 className="size-4" /> Saved
              </span>
            )}
            <button
              className="button-primary"
              type="submit"
              disabled={update.isPending || form.chunk_overlap >= form.chunk_size}
            >
              {update.isPending ? 'Saving…' : 'Save settings'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
