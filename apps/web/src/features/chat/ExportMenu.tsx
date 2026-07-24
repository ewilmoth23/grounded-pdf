import { Download } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';

interface Props {
  conversationId: string;
  /** Export is unavailable while streaming and before the first saved message. */
  disabled?: boolean;
}

/**
 * Download menu for the conversation header. The links point straight at the
 * server-side export endpoint, which renders entirely from persisted records —
 * nothing in browser state is part of the exported file.
 */
export function ExportMenu({ conversationId, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

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

  const itemClass =
    'flex w-full items-center rounded-lg px-3 py-2 text-sm text-ink-700 transition-colors duration-150 hover:bg-ink-50 hover:text-ink-950 dark:text-ink-200 dark:hover:bg-ink-800 dark:hover:text-white';

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
        className="button-ghost px-2"
        onClick={() => setOpen((value) => !value)}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label="Export conversation"
        title={
          disabled ? 'Export becomes available once the conversation has saved messages.' : 'Export'
        }
      >
        <Download className="size-5" aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Export conversation"
          className="absolute right-0 z-20 mt-2 w-44 rounded-xl border bg-white p-2 shadow-xl dark:bg-ink-900 dark:ring-1 dark:ring-white/[0.06]"
        >
          <a
            role="menuitem"
            className={itemClass}
            href={api.conversations.exportUrl(conversationId, 'markdown')}
            onClick={() => setOpen(false)}
          >
            Markdown (.md)
          </a>
          <a
            role="menuitem"
            className={itemClass}
            href={api.conversations.exportUrl(conversationId, 'html')}
            onClick={() => setOpen(false)}
          >
            HTML (.html)
          </a>
        </div>
      )}
    </div>
  );
}
