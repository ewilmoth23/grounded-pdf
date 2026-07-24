import { ChevronDown, FileText } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { DocumentRecord } from '../../types/api';

interface Props {
  documents: DocumentRecord[];
  selected: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
}

function triggerLabel(documents: DocumentRecord[], selected: string[]): string {
  if (!selected.length) return 'Select documents';
  const names = selected
    .map((id) => {
      const doc = documents.find((candidate) => candidate.id === id);
      return doc ? (doc.title ?? doc.original_name) : null;
    })
    .filter((name): name is string => Boolean(name));
  const shown = names.slice(0, 2).join(', ');
  const extra = selected.length - Math.min(names.length, 2);
  if (!shown) return `${selected.length} document${selected.length === 1 ? '' : 's'} selected`;
  return extra > 0 ? `${shown} +${extra}` : shown;
}

export function DocumentPicker({ documents, selected, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Close when streaming starts (the picker is disabled for the duration).
  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open]);

  function close() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  const available = documents.filter((doc) => doc.status === 'ready' || selected.includes(doc.id));
  return (
    <div
      className="relative"
      ref={containerRef}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) {
          event.stopPropagation();
          close();
        }
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        className="button-secondary max-w-full"
        onClick={() => setOpen((value) => !value)}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <FileText className="size-4 shrink-0" />
        <span className="max-w-52 truncate">{triggerLabel(documents, selected)}</span>
        <ChevronDown
          className={`size-4 shrink-0 transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 max-h-72 w-[min(22rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border bg-white p-2 shadow-xl dark:bg-ink-900 dark:ring-1 dark:ring-white/[0.06]">
          {available.length === 0 ? (
            <p className="p-3 text-sm text-ink-500 dark:text-ink-300">
              No processed documents are ready.
            </p>
          ) : (
            available.map((doc) => {
              const checked = selected.includes(doc.id);
              return (
                <label
                  key={doc.id}
                  className="flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors duration-150 hover:bg-ink-50 dark:hover:bg-ink-800"
                >
                  <input
                    type="checkbox"
                    className="size-4 shrink-0 accent-accent-700 dark:accent-accent-500"
                    checked={checked}
                    disabled={disabled}
                    onChange={() =>
                      onChange(
                        checked ? selected.filter((id) => id !== doc.id) : [...selected, doc.id],
                      )
                    }
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{doc.title ?? doc.original_name}</span>
                    {doc.status !== 'ready' && (
                      <span className="block text-xs capitalize text-ink-500 dark:text-ink-400">
                        {doc.status} · uncheck to remove
                      </span>
                    )}
                  </span>
                </label>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
