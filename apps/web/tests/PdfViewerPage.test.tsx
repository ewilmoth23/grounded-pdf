import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { Route, Routes } from 'react-router';
import { vi } from 'vitest';
import { PdfViewerPage } from '../src/pages/PdfViewerPage';
import { jsonResponse, renderApp } from './helpers';

vi.mock('react-pdf', () => ({
  pdfjs: { version: 'test', GlobalWorkerOptions: {} },
  Document: ({ children }: { children?: ReactNode }) => (
    <div data-testid="pdf-document">{children}</div>
  ),
  Page: ({ pageNumber }: { pageNumber: number }) => (
    <div data-testid="pdf-page">Rendered page {pageNumber}</div>
  ),
}));

const documentDetail = {
  id: 'doc-1',
  original_name: 'report.pdf',
  title: 'Annual Report',
  file_size: 4200,
  page_count: 6,
  searchable_page_count: 6,
  status: 'ready',
  processing_error: null,
  stale_index: false,
  created_at: '2026-01-01T12:00:00Z',
  updated_at: '2026-01-01T12:00:00Z',
  scanned_page_numbers: [],
  chunk_count: 12,
  outline: [
    { level: 1, title: 'Introduction', page: 1 },
    { level: 2, title: 'Methods', page: 2 },
    { level: 1, title: 'Findings', page: 4 },
  ],
};

function renderViewer(detail: unknown = documentDetail) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/documents/doc-1/file')) {
        return Promise.resolve(new Response(new Blob(), { status: 200 }));
      }
      return Promise.resolve(jsonResponse(detail));
    }),
  );
  return renderApp(
    <Routes>
      <Route path="/documents/:documentId/view" element={<PdfViewerPage />} />
    </Routes>,
    { initialEntries: ['/documents/doc-1/view?page=1'] },
  );
}

test('shows the outline sidebar and navigates to the selected section', async () => {
  renderViewer();

  const toggle = await screen.findByRole('button', { name: 'Show document outline' });
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await userEvent.click(toggle);

  const nav = screen.getByRole('navigation', { name: 'Document outline' });
  expect(nav).toBeVisible();
  expect(screen.getByRole('button', { name: 'Introduction' })).toHaveAttribute(
    'aria-current',
    'true',
  );
  expect(screen.getByRole('button', { name: 'Findings' })).not.toHaveAttribute('aria-current');

  await userEvent.click(screen.getByRole('button', { name: 'Findings' }));

  await waitFor(() => expect(screen.getByText('Cited page 4')).toBeVisible());
  expect(screen.getByLabelText('Page number')).toHaveValue(4);
});

test('hides the outline control when the document has no outline', async () => {
  renderViewer({ ...documentDetail, outline: null });

  expect(await screen.findByTestId('pdf-document')).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.queryByRole('button', { name: 'Show document outline' })).not.toBeInTheDocument(),
  );
});
