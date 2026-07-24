import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ConversationNav } from '../src/features/chat/ConversationNav';
import { DocumentPicker } from '../src/features/chat/DocumentPicker';
import { MessageBubble } from '../src/features/chat/MessageBubble';
import { renderApp } from './helpers';

test('renders structured citations linked to the correct page', () => {
  renderApp(
    <MessageBubble
      message={{
        id: 'message-1',
        role: 'assistant',
        content: 'The gain was 37 percent. [sample.pdf, p. 2]',
        created_at: '2026-01-01T00:00:00Z',
        citations: [
          {
            id: 'citation-1',
            document_id: 'doc-1',
            document_name: 'sample.pdf',
            page_number: 2,
            excerpt: 'The measured efficiency gain was 37 percent.',
            retrieval_score: 0.91,
            ordinal: 1,
          },
        ],
      }}
    />,
  );
  expect(screen.getByText('Sources (1)')).toBeInTheDocument();
  const source = screen.getByRole('link', { name: 'Open sample.pdf page 2' });
  expect(source).toHaveAttribute(
    'href',
    `/documents/doc-1/view?page=2&highlight=${encodeURIComponent(
      'The measured efficiency gain was 37 percent.',
    )}`,
  );
});

test('citations from deleted documents render as non-clickable snapshots', () => {
  renderApp(
    <MessageBubble
      message={{
        id: 'message-1',
        role: 'assistant',
        content: 'The gain was 37 percent. [sample.pdf, p. 2]',
        created_at: '2026-01-01T00:00:00Z',
        citations: [
          {
            id: 'citation-1',
            document_id: null,
            document_name: 'sample.pdf',
            page_number: 2,
            excerpt: 'The measured efficiency gain was 37 percent.',
            retrieval_score: 0.91,
            ordinal: 1,
          },
        ],
      }}
    />,
  );
  expect(screen.getByText('Sources (1)')).toBeInTheDocument();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  expect(screen.getByText('Source deleted')).toBeInTheDocument();
  expect(screen.getByText('The measured efficiency gain was 37 percent.')).toBeInTheDocument();
  expect(screen.getByLabelText('sample.pdf page 2 (source deleted)')).toBeInTheDocument();
});

test('citation sources are collapsed by default', () => {
  renderApp(
    <MessageBubble
      message={{
        id: 'message-1',
        role: 'assistant',
        content: 'Answer',
        created_at: '2026-01-01T00:00:00Z',
        citations: [
          {
            id: 'citation-1',
            document_id: 'doc-1',
            document_name: 'sample.pdf',
            page_number: 2,
            excerpt: 'Excerpt',
            retrieval_score: 0.91,
            ordinal: 1,
          },
        ],
      }}
    />,
  );
  const details = screen.getByText('Sources (1)').closest('details');
  expect(details).not.toHaveAttribute('open');
});

test('document picker only offers ready documents and keeps the popover open on toggle', async () => {
  const changes: string[][] = [];
  renderApp(
    <DocumentPicker
      documents={[
        {
          id: 'ready',
          original_name: 'ready.pdf',
          title: null,
          file_size: 1,
          page_count: 1,
          searchable_page_count: 1,
          status: 'ready',
          processing_error: null,
          stale_index: false,
          created_at: '',
          updated_at: '',
        },
        {
          id: 'failed',
          original_name: 'failed.pdf',
          title: null,
          file_size: 1,
          page_count: 1,
          searchable_page_count: 0,
          status: 'failed',
          processing_error: 'bad',
          stale_index: false,
          created_at: '',
          updated_at: '',
        },
      ]}
      selected={[]}
      onChange={(ids) => changes.push(ids)}
    />,
  );
  await userEvent.click(screen.getByRole('button', { name: /Select documents/ }));
  expect(screen.getByText('ready.pdf')).toBeInTheDocument();
  expect(screen.queryByText('failed.pdf')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('checkbox', { name: /ready.pdf/ }));
  expect(changes).toEqual([['ready']]);
  // Toggling a document must not dismiss the popover.
  expect(screen.getByRole('checkbox', { name: /ready.pdf/ })).toBeInTheDocument();
});

test('document picker closes on Escape and returns focus to the trigger', async () => {
  renderApp(
    <DocumentPicker
      documents={[
        {
          id: 'ready',
          original_name: 'ready.pdf',
          title: null,
          file_size: 1,
          page_count: 1,
          searchable_page_count: 1,
          status: 'ready',
          processing_error: null,
          stale_index: false,
          created_at: '',
          updated_at: '',
        },
      ]}
      selected={[]}
      onChange={() => undefined}
    />,
  );
  const trigger = screen.getByRole('button', { name: /Select documents/ });
  await userEvent.click(trigger);
  expect(screen.getByRole('checkbox', { name: /ready.pdf/ })).toBeInTheDocument();
  await userEvent.keyboard('{Escape}');
  expect(screen.queryByRole('checkbox', { name: /ready.pdf/ })).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute('aria-expanded', 'false');
});

test('document picker lets users remove a selected document that is no longer ready', async () => {
  const changes: string[][] = [];
  renderApp(
    <DocumentPicker
      documents={[
        {
          id: 'failed',
          original_name: 'failed.pdf',
          title: null,
          file_size: 1,
          page_count: 1,
          searchable_page_count: 0,
          status: 'failed',
          processing_error: 'bad',
          stale_index: false,
          created_at: '',
          updated_at: '',
        },
      ]}
      selected={['failed']}
      onChange={(ids) => changes.push(ids)}
    />,
  );

  await userEvent.click(screen.getByRole('button', { name: /failed.pdf/ }));
  await userEvent.click(screen.getByRole('checkbox', { name: /failed.pdf/i }));
  expect(changes).toEqual([[]]);
});

test('document picker closes and blocks changes when a stream starts', async () => {
  const changes: string[][] = [];
  const document = {
    id: 'ready',
    original_name: 'ready.pdf',
    title: null,
    file_size: 1,
    page_count: 1,
    searchable_page_count: 1,
    status: 'ready' as const,
    processing_error: null,
    stale_index: false,
    created_at: '',
    updated_at: '',
  };
  const { rerender } = render(
    <DocumentPicker documents={[document]} selected={[]} onChange={(ids) => changes.push(ids)} />,
  );
  await userEvent.click(screen.getByRole('button', { name: /Select documents/ }));
  expect(screen.getByRole('checkbox', { name: /ready.pdf/ })).toBeVisible();

  rerender(
    <DocumentPicker
      documents={[document]}
      selected={[]}
      onChange={(ids) => changes.push(ids)}
      disabled
    />,
  );

  expect(screen.queryByRole('checkbox', { name: /ready.pdf/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Select documents/ })).toBeDisabled();
  expect(changes).toEqual([]);
});

test('conversation mutations are disabled while chat is busy', () => {
  renderApp(
    <ConversationNav
      conversations={[
        {
          id: 'conversation-1',
          title: 'Research',
          document_ids: [],
          created_at: '',
          updated_at: '',
        },
      ]}
      activeId="conversation-1"
      onCreate={() => undefined}
      onRename={() => undefined}
      onDelete={() => undefined}
      busy
    />,
  );

  expect(screen.getByRole('button', { name: 'New conversation' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Rename Research' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Delete Research' })).toBeDisabled();
});

test('renames a conversation inline with Enter and cancels with Escape', async () => {
  const renames: Array<{ id: string; title: string }> = [];
  renderApp(
    <ConversationNav
      conversations={[
        {
          id: 'conversation-1',
          title: 'Research',
          document_ids: [],
          created_at: '',
          updated_at: '',
        },
      ]}
      activeId="conversation-1"
      onCreate={() => undefined}
      onRename={(conversation, title) => renames.push({ id: conversation.id, title })}
      onDelete={() => undefined}
      busy={false}
    />,
  );

  await userEvent.click(screen.getByRole('button', { name: 'Rename Research' }));
  const input = screen.getByRole('textbox', { name: 'Rename Research' });
  await userEvent.clear(input);
  await userEvent.type(input, 'Q3 findings{Enter}');
  expect(renames).toEqual([{ id: 'conversation-1', title: 'Q3 findings' }]);

  await userEvent.click(screen.getByRole('button', { name: 'Rename Research' }));
  await userEvent.type(screen.getByRole('textbox', { name: 'Rename Research' }), ' extra{Escape}');
  expect(renames).toHaveLength(1);
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});

test('deleting is requested through the provided handler', async () => {
  const onDelete = vi.fn();
  renderApp(
    <ConversationNav
      conversations={[
        {
          id: 'conversation-1',
          title: 'Research',
          document_ids: [],
          created_at: '',
          updated_at: '',
        },
      ]}
      activeId="conversation-1"
      onCreate={() => undefined}
      onRename={() => undefined}
      onDelete={onDelete}
      busy={false}
    />,
  );
  await userEvent.click(screen.getByRole('button', { name: 'Delete Research' }));
  expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ id: 'conversation-1' }));
});

test('compare answers render per-document section panels in a responsive grid', () => {
  renderApp(
    <MessageBubble
      message={{
        id: 'message-1',
        role: 'assistant',
        mode: 'compare',
        content:
          '## alpha.pdf\n\nThe gain was 37 percent. [alpha.pdf, p. 2]\n\n## beta.pdf\n\n' +
          "I couldn't find enough evidence in the selected documents to answer that question.",
        created_at: '2026-01-01T00:00:00Z',
        citations: [
          {
            id: 'citation-1',
            document_id: 'doc-1',
            document_name: 'alpha.pdf',
            page_number: 2,
            excerpt: 'The measured efficiency gain was 37 percent.',
            retrieval_score: 0.91,
            ordinal: 1,
          },
        ],
      }}
    />,
  );
  const grid = screen.getByTestId('compare-sections');
  expect(grid.className).toContain('lg:grid-cols-2');
  const headings = screen.getAllByRole('heading', { level: 3 });
  expect(headings.map((heading) => heading.textContent)).toEqual(['alpha.pdf', 'beta.pdf']);
  expect(screen.getByLabelText('Answer from beta.pdf')).toHaveTextContent(
    "I couldn't find enough evidence",
  );
  // Sources stay shared beneath the sections.
  expect(screen.getByText('Sources (1)')).toBeInTheDocument();
});

test('assistant markdown headings without compare mode keep the regular layout', () => {
  renderApp(
    <MessageBubble
      message={{
        id: 'message-1',
        role: 'assistant',
        mode: null,
        content: '## First\n\nText.\n\n## Second\n\nMore text.',
        created_at: '2026-01-01T00:00:00Z',
        citations: [],
      }}
    />,
  );
  expect(screen.queryByTestId('compare-sections')).not.toBeInTheDocument();
});

test('streaming answer is visibly marked', () => {
  renderApp(
    <MessageBubble
      streaming
      message={{
        id: 'streaming',
        role: 'assistant',
        content: 'Partial answer',
        citations: [],
        created_at: '',
      }}
    />,
  );
  expect(screen.getByLabelText('Answer streaming')).toBeInTheDocument();
});
