import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { SettingsPage } from '../src/pages/SettingsPage';
import { jsonResponse, renderApp } from './helpers';

const settings = {
  environment: 'development',
  model_provider: 'ollama',
  model_name: 'llama3.2:3b',
  embedding_model: 'sentence-transformers/all-MiniLM-L6-v2',
  chunk_size: 900,
  chunk_overlap: 150,
  retrieval_count: 6,
  max_upload_mb: 50,
  max_upload_batch_mb: 200,
  max_upload_files: 20,
  temperature: 0.1,
  max_output_tokens: 800,
  ocr_enabled: false,
};

test('validates chunk overlap before saving', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(settings)));
  renderApp(<SettingsPage />);
  const overlap = await screen.findByLabelText('Chunk overlap');
  await userEvent.clear(overlap);
  await userEvent.type(overlap, '900');
  expect(screen.getByRole('alert')).toHaveTextContent('Chunk overlap must be smaller');
  expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled();
});

test('changes theme preference locally', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(settings)));
  renderApp(<SettingsPage />);
  await screen.findByText('Embedding model');
  await userEvent.click(screen.getByRole('button', { name: 'Dark' }));
  expect(document.documentElement).toHaveClass('dark');
  expect(window.localStorage.getItem('groundedpdf-theme')).toBe('dark');
});

test('does not overwrite unsaved edits when settings refetch', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(settings)));
  const { queryClient } = renderApp(<SettingsPage />);
  const modelName = await screen.findByLabelText('Chat model');
  await userEvent.clear(modelName);
  await userEvent.type(modelName, 'my-unsaved-model');

  queryClient.setQueryData(['settings'], { ...settings, model_name: 'server-refetch-model' });

  await waitFor(() => expect(screen.getByLabelText('Chat model')).toHaveValue('my-unsaved-model'));
});
