import { Edit3, MessageSquare, Plus, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { NavLink } from 'react-router';
import type { Conversation } from '../../types/api';

interface Props {
  conversations: Conversation[];
  activeId?: string;
  onCreate: () => void;
  onRename: (conversation: Conversation, title: string) => void;
  onDelete: (conversation: Conversation) => void;
  busy: boolean;
}

const rowActionClasses =
  'opacity-0 transition-opacity duration-150 focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100';

export function ConversationNav({
  conversations,
  activeId,
  onCreate,
  onRename,
  onDelete,
  busy,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingId) editInputRef.current?.focus();
  }, [editingId]);

  function startEditing(conversation: Conversation) {
    setEditingId(conversation.id);
    setDraftTitle(conversation.title);
  }

  function commitEditing(conversation: Conversation) {
    const title = draftTitle.trim();
    setEditingId(null);
    if (title && title !== conversation.title) onRename(conversation, title);
  }

  return (
    <aside className="flex h-full flex-col border-r bg-white dark:bg-ink-900">
      <div className="border-b p-3">
        <button type="button" className="button-primary w-full" onClick={onCreate} disabled={busy}>
          <Plus className="size-4" /> New conversation
        </button>
      </div>
      <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2" aria-label="Conversations">
        {conversations.map((conversation) => (
          <div key={conversation.id} className="group relative">
            {editingId === conversation.id ? (
              <input
                ref={editInputRef}
                className="field min-h-11 py-2 text-sm"
                value={draftTitle}
                maxLength={200}
                aria-label={`Rename ${conversation.title}`}
                onChange={(event) => setDraftTitle(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    commitEditing(conversation);
                  } else if (event.key === 'Escape') {
                    event.stopPropagation();
                    setEditingId(null);
                  }
                }}
                onBlur={() => setEditingId(null)}
              />
            ) : (
              <>
                <NavLink
                  to={`/chat/${conversation.id}`}
                  className={`flex min-h-11 items-center gap-2 rounded-lg py-2 pl-3 pr-16 text-sm transition-colors duration-150 ${
                    activeId === conversation.id
                      ? 'bg-accent-50 font-semibold text-accent-800 dark:bg-accent-950 dark:text-accent-200'
                      : 'text-ink-600 hover:bg-ink-50 dark:text-ink-300 dark:hover:bg-ink-800'
                  }`}
                >
                  <MessageSquare className="size-4 shrink-0" />
                  <span className="truncate">{conversation.title}</span>
                </NavLink>
                <div className={`absolute right-1 top-1 flex ${rowActionClasses}`}>
                  <button
                    type="button"
                    className="button-ghost min-h-9 px-1.5 focus-visible:opacity-100"
                    onClick={() => startEditing(conversation)}
                    disabled={busy}
                    aria-label={`Rename ${conversation.title}`}
                  >
                    <Edit3 className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    className="button-ghost min-h-9 px-1.5 hover:text-red-700 focus-visible:opacity-100 dark:hover:text-red-300"
                    onClick={() => onDelete(conversation)}
                    disabled={busy}
                    aria-label={`Delete ${conversation.title}`}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
        {conversations.length === 0 && (
          <p className="px-3 py-6 text-center text-xs text-ink-500 dark:text-ink-400">
            No conversations yet
          </p>
        )}
      </nav>
    </aside>
  );
}
