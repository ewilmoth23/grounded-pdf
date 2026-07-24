import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router';
import { vi } from 'vitest';
import { ChatPage } from '../src/pages/ChatPage';
import type { DocumentRecord, Message } from '../src/types/api';
import { jsonResponse, renderApp } from './helpers';

function documentRecord(id: string, status: DocumentRecord['status'] = 'ready'): DocumentRecord {
  return {
    id,
    original_name: `${id}.pdf`,
    title: null,
    file_size: 1,
    page_count: 1,
    searchable_page_count: 1,
    status,
    processing_error: null,
    stale_index: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function mockConversationFetch(
  documents: DocumentRecord[],
  selectedIds: string[],
  messages: Message[] = [],
) {
  const conversation = {
    id: 'c1',
    title: 'Research',
    document_ids: selectedIds,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    // List endpoints carry limit/offset query parameters; match on the path.
    const path = new URL(url, 'http://localhost').pathname;
    if (path.endsWith('/documents')) return Promise.resolve(jsonResponse(documents));
    if (path.endsWith('/conversations/c1')) {
      return Promise.resolve(jsonResponse({ ...conversation, messages }));
    }
    if (path.endsWith('/conversations')) return Promise.resolve(jsonResponse([conversation]));
    return Promise.resolve(jsonResponse([]));
  });
  vi.stubGlobal('fetch', fetchMock);
}

function savedExchange(): Message[] {
  return [
    {
      id: 'm1',
      role: 'user',
      content: 'What was the result?',
      mode: null,
      citations: [],
      created_at: '2026-01-01T00:01:00Z',
    },
    {
      id: 'm2',
      role: 'assistant',
      content: 'The result was 37 percent [ready-1.pdf, p. 2].',
      mode: null,
      citations: [],
      created_at: '2026-01-01T00:02:00Z',
    },
  ];
}

function renderChatRoute() {
  renderApp(
    <Routes>
      <Route path="/chat/:conversationId" element={<ChatPage />} />
    </Routes>,
    { initialEntries: ['/chat/c1'] },
  );
}

test('shows conversation creation failures without requiring an active conversation', async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    if (url.endsWith('/conversations') && init?.method === 'POST') {
      return Promise.resolve(
        jsonResponse(
          { error: { code: 'database_unavailable', message: 'Could not create conversation' } },
          503,
        ),
      );
    }
    return Promise.resolve(jsonResponse([]));
  });
  vi.stubGlobal('fetch', fetchMock);
  renderApp(<ChatPage />);

  await screen.findByText('Start a grounded conversation');
  const createButtons = screen.getAllByRole('button', { name: 'New conversation' });
  await userEvent.click(createButtons.at(-1)!);

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not create conversation');
});

test('export menu is disabled while the conversation has no saved messages', async () => {
  mockConversationFetch([documentRecord('ready-1')], ['ready-1']);
  renderChatRoute();

  const exportButton = await screen.findByRole('button', { name: 'Export conversation' });
  expect(exportButton).toBeDisabled();
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
});

test('export menu offers markdown and html downloads of the saved conversation', async () => {
  mockConversationFetch([documentRecord('ready-1')], ['ready-1'], savedExchange());
  renderChatRoute();

  await screen.findByText('What was the result?');
  const exportButton = await screen.findByRole('button', { name: 'Export conversation' });
  expect(exportButton).toBeEnabled();
  expect(exportButton).toHaveAttribute('aria-expanded', 'false');

  await userEvent.click(exportButton);

  expect(exportButton).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByRole('menuitem', { name: 'Markdown (.md)' })).toHaveAttribute(
    'href',
    expect.stringContaining('/conversations/c1/export?format=markdown'),
  );
  expect(screen.getByRole('menuitem', { name: 'HTML (.html)' })).toHaveAttribute(
    'href',
    expect.stringContaining('/conversations/c1/export?format=html'),
  );
});

test('compare toggle is disabled until two ready documents are selected', async () => {
  mockConversationFetch(
    [documentRecord('ready-1'), documentRecord('processing-1', 'processing')],
    ['ready-1', 'processing-1'],
  );
  renderChatRoute();

  const compareButton = await screen.findByRole('button', { name: /Compare docs/ });
  expect(compareButton).toBeDisabled();
  expect(compareButton).toHaveAttribute('title', 'Select at least two ready documents to compare.');
  expect(screen.getByRole('button', { name: /Answer/ })).toHaveAttribute('aria-pressed', 'true');
});

test('compare toggle activates with two ready documents and swaps the suggested prompts', async () => {
  mockConversationFetch(
    [documentRecord('ready-1'), documentRecord('ready-2')],
    ['ready-1', 'ready-2'],
  );
  renderChatRoute();

  const compareButton = await screen.findByRole('button', { name: /Compare docs/ });
  expect(compareButton).toBeEnabled();
  expect(await screen.findByText('Summarize the key findings')).toBeInTheDocument();

  await userEvent.click(compareButton);

  expect(compareButton).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByText('Compare the methodologies')).toBeInTheDocument();
  expect(screen.queryByText('Summarize the key findings')).not.toBeInTheDocument();
});
