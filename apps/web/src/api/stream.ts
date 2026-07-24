import { API_BASE, ApiError, toApiError } from './client';
import type { Citation, Message, QuestionMode } from '../types/api';

interface StreamHandlers {
  onMetadata: (payload: { user_message: Message; citations: Citation[] }) => void;
  onToken: (token: string) => void;
  onDone: (message: Message) => void;
}

function dispatchEvent(event: string, data: string, handlers: StreamHandlers): void {
  let payload: unknown;
  try {
    payload = JSON.parse(data) as unknown;
  } catch {
    throw new ApiError('The answer stream sent a malformed frame.', 'stream_malformed_frame', 502);
  }
  if (event === 'metadata') {
    handlers.onMetadata(payload as { user_message: Message; citations: Citation[] });
  } else if (event === 'token') {
    handlers.onToken((payload as { token: string }).token);
  } else if (event === 'done') {
    handlers.onDone(payload as Message);
  } else if (event === 'error') {
    const error = payload as { code: string; message: string; status?: number };
    throw new ApiError(error.message, error.code, error.status ?? 503);
  }
}

export async function streamQuestion(
  conversationId: string,
  question: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
  mode: QuestionMode = 'answer',
): Promise<void> {
  const response = await fetch(`${API_BASE}/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ question, mode }),
    signal,
  });
  if (!response.ok || !response.body) {
    const payload = (await response.json().catch(() => null)) as unknown;
    throw toApiError(payload, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let completed = false;

  function processBlock(block: string): void {
    let event = 'message';
    const data: string[] = [];
    for (const rawLine of block.split('\n')) {
      const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
      // Ignore comments and fields we do not use (id:, retry:, …).
      if (!line || line.startsWith(':')) continue;
      if (line.startsWith('event:')) {
        event = line.slice(6).replace(/^ /, '');
      } else if (line.startsWith('data:')) {
        data.push(line.slice(5).replace(/^ /, ''));
      }
    }
    if (!data.length) return;
    if (event === 'done') completed = true;
    dispatchEvent(event, data.join('\n'), handlers);
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? '';
      blocks.forEach(processBlock);
    }
    buffer += decoder.decode();
    if (buffer.trim()) processBlock(buffer);
  } finally {
    await reader.cancel().catch(() => undefined);
  }
  if (!completed) {
    throw new ApiError(
      'The answer stream ended before the server confirmed completion.',
      'stream_incomplete',
      502,
    );
  }
}
