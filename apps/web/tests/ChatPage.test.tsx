import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ChatPage } from '../src/pages/ChatPage';
import { jsonResponse, renderApp } from './helpers';

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
