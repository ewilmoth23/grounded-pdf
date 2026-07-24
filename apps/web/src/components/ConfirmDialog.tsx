import { AlertTriangle } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';
import { useModalBehavior } from '../hooks/useModalBehavior';

interface Props {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useModalBehavior(open, onCancel);
  useEffect(() => {
    if (open) cancelRef.current?.focus();
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center p-4 sm:items-center">
      <div className="absolute inset-0 bg-black/40" aria-hidden="true" onClick={onCancel} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="panel relative w-full max-w-md p-5 motion-safe:animate-message-in sm:p-6"
      >
        <div className="flex items-start gap-3">
          {danger && (
            <span className="rounded-lg bg-red-100 p-2 text-red-700 dark:bg-red-950 dark:text-red-300">
              <AlertTriangle className="size-5" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0">
            <h2 id="confirm-dialog-title" className="font-semibold">
              {title}
            </h2>
            <div className="mt-1.5 text-sm text-ink-500 dark:text-ink-300">{description}</div>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            className="button-secondary"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            className={danger ? 'button-danger' : 'button-primary'}
            onClick={onConfirm}
            disabled={busy}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
