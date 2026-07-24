import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { DocumentsPage } from '../src/pages/DocumentsPage';
import { jsonResponse, renderApp } from './helpers';

const failedDocument = {
  id: 'doc-1',
  original_name: 'scan.pdf',
  title: null,
  file_size: 4200,
  page_count: 0,
  searchable_page_count: 0,
  status: 'failed',
  processing_error: 'No searchable text was found.',
  created_at: '2026-01-01T12:00:00Z',
  updated_at: '2026-01-01T12:00:00Z',
};

test('renders the empty document state', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([])));
  renderApp(<DocumentsPage />);
  expect(await screen.findByText('No documents yet')).toBeInTheDocument();
});

test('shows failed processing details and retry action', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([failedDocument])));
  renderApp(<DocumentsPage />);
  expect(await screen.findByText('No searchable text was found.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Retry scan.pdf' })).toBeInTheDocument();
});

test('warns when a ready PDF contains unsearchable pages', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      jsonResponse([
        {
          ...failedDocument,
          status: 'ready',
          processing_error: null,
          page_count: 4,
          searchable_page_count: 2,
        },
      ]),
    ),
  );
  renderApp(<DocumentsPage />);
  expect(
    await screen.findByText('2 pages have no searchable text and may be scanned.'),
  ).toBeVisible();
});

test('offers retry guidance for an interrupted deletion tombstone', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        jsonResponse([{ ...failedDocument, status: 'deleted', processing_error: null }]),
      ),
  );
  renderApp(<DocumentsPage />);
  expect(
    await screen.findByText('Deletion was interrupted. Retry deletion to finish cleanup.'),
  ).toBeVisible();
  expect(screen.getByRole('button', { name: 'Retry deletion of scan.pdf' })).toBeVisible();
});

test('shows upload progress and rejected-file feedback', async () => {
  let resolveUpload: ((value: Response) => void) | undefined;
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse([]))
    .mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveUpload = resolve;
        }),
    )
    .mockResolvedValue(jsonResponse([]));
  vi.stubGlobal('fetch', fetchMock);
  renderApp(<DocumentsPage />);
  await screen.findByText('No documents yet');
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await userEvent.upload(input, new File(['invalid'], 'sample.pdf', { type: 'application/pdf' }));
  expect(await screen.findByText('Uploading and validating…')).toBeInTheDocument();
  expect(input).toBeDisabled();
  expect(screen.getByRole('button', { name: /Uploading and validating/i })).toHaveAttribute(
    'aria-disabled',
    'true',
  );
  resolveUpload?.(
    jsonResponse(
      {
        documents: [],
        rejected: [
          { filename: 'sample.pdf', code: 'invalid_signature', message: 'The PDF is invalid' },
        ],
      },
      202,
    ),
  );
  expect(await screen.findByText(/sample.pdf: The PDF is invalid/)).toBeInTheDocument();
});

test('renders API errors', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ error: { code: 'offline', message: 'API unavailable' } }, 503),
      ),
  );
  renderApp(<DocumentsPage />);
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('API unavailable'));
});

test('flags stale documents and reprocesses them in one click', async () => {
  const staleDocument = {
    ...failedDocument,
    status: 'ready',
    processing_error: null,
    page_count: 4,
    searchable_page_count: 4,
    stale_index: true,
  };
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse([staleDocument]))
    .mockResolvedValueOnce(jsonResponse({ queued: 1, remaining: 0 }, 202))
    .mockImplementation(() =>
      Promise.resolve(jsonResponse([{ ...staleDocument, status: 'queued', stale_index: false }])),
    );
  vi.stubGlobal('fetch', fetchMock);
  renderApp(<DocumentsPage />);

  expect(
    await screen.findByText(/1 document was indexed with different settings/),
  ).toBeInTheDocument();
  expect(screen.getByText('Index outdated')).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: 'Reprocess 1 document' }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/documents/reprocess-stale'),
      expect.objectContaining({ method: 'POST' }),
    ),
  );
  await waitFor(() =>
    expect(
      screen.queryByText(/1 document was indexed with different settings/),
    ).not.toBeInTheDocument(),
  );
});

test('does not show the reprocess banner when no document is stale', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      jsonResponse([
        {
          ...failedDocument,
          status: 'ready',
          processing_error: null,
          page_count: 4,
          searchable_page_count: 4,
          stale_index: false,
        },
      ]),
    ),
  );
  renderApp(<DocumentsPage />);
  expect(await screen.findByText('scan.pdf')).toBeInTheDocument();
  expect(screen.queryByText(/indexed with different settings/)).not.toBeInTheDocument();
  expect(screen.queryByText('Index outdated')).not.toBeInTheDocument();
});

test('supports drag and drop file selection', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse([]))
    .mockResolvedValueOnce(jsonResponse({ documents: [], rejected: [] }, 202))
    .mockResolvedValue(jsonResponse([]));
  vi.stubGlobal('fetch', fetchMock);
  renderApp(<DocumentsPage />);
  const dropzone = await screen.findByRole('button', { name: /Drop PDF files here/i });
  const file = new File(['%PDF-'], 'sample.pdf', { type: 'application/pdf' });
  fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/documents'),
      expect.objectContaining({ method: 'POST' }),
    ),
  );
});
