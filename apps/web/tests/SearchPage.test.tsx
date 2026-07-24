import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { SearchPage } from '../src/pages/SearchPage';
import type { DocumentRecord, SearchResult } from '../src/types/api';
import { jsonResponse, renderApp } from './helpers';

const readyDocument: DocumentRecord = {
  id: 'doc-1',
  original_name: 'sample.pdf',
  title: null,
  file_size: 1000,
  page_count: 2,
  searchable_page_count: 2,
  status: 'ready',
  processing_error: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const searchResult: SearchResult = {
  query: 'efficiency gain',
  documents_available: true,
  matches: [
    {
      document_id: 'doc-1',
      document_name: 'sample.pdf',
      page_number: 2,
      excerpt: 'The measured efficiency gain was 37 percent.',
      score: 0.82,
    },
  ],
};

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  return input instanceof URL ? input.href : input.url;
}

function stubFetch(documents: DocumentRecord[], result: SearchResult) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = requestUrl(input);
    if (url.includes('/search?')) return Promise.resolve(jsonResponse(result));
    return Promise.resolve(jsonResponse(documents));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

test('search results render source cards linking into the highlighted viewer', async () => {
  stubFetch([readyDocument], searchResult);
  renderApp(<SearchPage />);

  await userEvent.type(screen.getByRole('searchbox'), 'efficiency gain');

  const link = await screen.findByRole('link', { name: 'Open sample.pdf page 2' });
  expect(link).toHaveAttribute(
    'href',
    `/documents/doc-1/view?page=2&highlight=${encodeURIComponent(
      'The measured efficiency gain was 37 percent.',
    )}`,
  );
  expect(within(link).getByText('p. 2')).toBeInTheDocument();
  expect(within(link).getByText('82% match')).toBeInTheDocument();
  // Query terms are emphasized client-side inside the stored excerpt.
  expect(link.querySelectorAll('mark').length).toBeGreaterThan(0);
  expect(screen.getByRole('status')).toHaveTextContent('1 passage found');
});

test('an empty match list shows the no-passages state', async () => {
  stubFetch([readyDocument], { query: 'nothing here', documents_available: true, matches: [] });
  renderApp(<SearchPage />);

  await userEvent.type(screen.getByRole('searchbox'), 'nothing here');

  expect(await screen.findByText('No matching passages')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Open/ })).not.toBeInTheDocument();
});

test('without ready documents the page explains and links to Documents', async () => {
  stubFetch([], { query: '', documents_available: false, matches: [] });
  renderApp(<SearchPage />);

  expect(await screen.findByText('No documents to search')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Go to Documents' })).toHaveAttribute(
    'href',
    '/documents',
  );
});

test('short queries do not trigger a search request', async () => {
  const fetchMock = stubFetch([readyDocument], searchResult);
  renderApp(<SearchPage />);

  await userEvent.type(screen.getByRole('searchbox'), 'ab');
  // Outlast the 350ms debounce window to prove the request was never scheduled.
  await new Promise((resolve) => setTimeout(resolve, 450));

  expect(screen.getByText(/Type at least 3 characters/)).toBeInTheDocument();
  const searchCalls = fetchMock.mock.calls.filter(([input]) =>
    requestUrl(input).includes('/search?'),
  );
  expect(searchCalls).toHaveLength(0);
});
