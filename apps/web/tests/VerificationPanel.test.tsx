import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { MessageBubble } from '../src/features/chat/MessageBubble';
import type { Message, Verification } from '../src/types/api';
import { jsonResponse, renderApp } from './helpers';

const assistantMessage: Message = {
  id: 'message-1',
  role: 'assistant',
  content: 'The gain was 37 percent. The colony was founded in 1999.',
  citations: [],
  created_at: '2026-01-01T00:00:00Z',
};

const verification: Verification = {
  message_id: 'message-1',
  generated_at: '2026-01-01T00:00:01Z',
  sentences: [
    {
      text: 'The gain was 37 percent.',
      verdict: 'supported',
      score: 0.91,
      source: {
        document_id: 'doc-1',
        document_name: 'sample.pdf',
        page_number: 2,
        excerpt: 'The measured efficiency gain was 37 percent.',
      },
    },
    {
      text: 'The colony was founded in 1999.',
      verdict: 'unsupported',
      score: 0.02,
      source: null,
    },
    {
      text: 'The pilot ran during 2024.',
      verdict: 'weak',
      score: 0.4,
      source: {
        document_id: 'doc-1',
        document_name: 'sample.pdf',
        page_number: 1,
        excerpt: 'The project began in 2024.',
      },
    },
  ],
};

test('verification panel orders verdicts, badges rows, and links to evidence', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(jsonResponse(verification))),
  );
  renderApp(<MessageBubble message={assistantMessage} conversationId="conversation-1" />);

  await userEvent.click(screen.getByRole('button', { name: /Verify answer/ }));

  expect(await screen.findByRole('status')).toHaveTextContent(
    '1 of 3 claims supported by your documents',
  );
  const rows = screen.getAllByRole('listitem');
  expect(rows).toHaveLength(3);
  expect(within(rows[0]).getByText('Not found')).toBeInTheDocument();
  expect(within(rows[0]).getByText('This claim was not found in your documents.')).toBeVisible();
  expect(within(rows[1]).getByText('Weak match')).toBeInTheDocument();
  expect(within(rows[2]).getByText('Supported')).toBeInTheDocument();

  const evidence = within(rows[2]).getByRole('link', {
    name: 'Open evidence in sample.pdf page 2',
  });
  expect(evidence).toHaveAttribute(
    'href',
    `/documents/doc-1/view?page=2&highlight=${encodeURIComponent(
      'The measured efficiency gain was 37 percent.',
    )}`,
  );
});

test('verification failures show an inline error with retry', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      jsonResponse({ error: { code: 'internal_error', message: 'Verification failed' } }, 500),
    )
    .mockResolvedValueOnce(jsonResponse(verification));
  vi.stubGlobal('fetch', fetchMock);
  renderApp(<MessageBubble message={assistantMessage} conversationId="conversation-1" />);

  await userEvent.click(screen.getByRole('button', { name: /Verify answer/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Verification failed');

  await userEvent.click(screen.getByRole('button', { name: /Retry/ }));
  expect(await screen.findByRole('status')).toHaveTextContent(
    '1 of 3 claims supported by your documents',
  );
});

test('verify action is hidden for unpersisted or streaming answers', () => {
  renderApp(
    <MessageBubble
      message={{ ...assistantMessage, id: 'stopped-123' }}
      conversationId="conversation-1"
    />,
  );
  expect(screen.queryByRole('button', { name: /Verify answer/ })).not.toBeInTheDocument();

  renderApp(<MessageBubble message={assistantMessage} conversationId="conversation-1" streaming />);
  expect(screen.queryByRole('button', { name: /Verify answer/ })).not.toBeInTheDocument();
});
