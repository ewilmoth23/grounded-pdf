import { vi } from 'vitest';
import { streamQuestion } from '../src/api/stream';

test('parses metadata, tokens, and completion across stream chunks', async () => {
  const encoder = new TextEncoder();
  const chunks = [
    'event: metadata\ndata: {"user_message":{"id":"u1","role":"user","content":"Q","citations":[],"created_at":""},"citations":[]}\n\n',
    'event: token\ndata: {"token":"Grounded "}\n\nevent: token\ndata: {"token":"answer"}\n\n',
    'event: done\ndata: {"id":"a1","role":"assistant","content":"Grounded answer","citations":[],"created_at":""}\n\n',
  ];
  const body = new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
  let answer = '';
  let complete = false;
  await streamQuestion('conversation', 'question', {
    onMetadata: () => undefined,
    onToken: (token) => {
      answer += token;
    },
    onDone: () => {
      complete = true;
    },
  });
  expect(answer).toBe('Grounded answer');
  expect(complete).toBe(true);
});

test('parses CRLF frames, unspaced data fields, and ignores comments/id/retry', async () => {
  const encoder = new TextEncoder();
  const chunks = [
    ': keep-alive comment\r\n\r\n',
    'event: token\r\ndata:{"token":"Grounded "}\r\n\r\n',
    'id: 7\nretry: 1000\nevent: token\ndata:{"token":"answer"}\n\n',
    'event: done\ndata: {"id":"a1","role":"assistant","content":"Grounded answer","citations":[],"created_at":""}\n\n',
  ];
  const body = new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
  let answer = '';
  let complete = false;
  await streamQuestion('conversation', 'question', {
    onMetadata: () => undefined,
    onToken: (token) => {
      answer += token;
    },
    onDone: () => {
      complete = true;
    },
  });
  expect(answer).toBe('Grounded answer');
  expect(complete).toBe(true);
});

test('surfaces malformed frames as a typed stream error instead of a SyntaxError', async () => {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode('event: token\ndata: {not json\n\n'));
      controller.close();
    },
  });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })));

  await expect(
    streamQuestion('conversation', 'question', {
      onMetadata: () => undefined,
      onToken: () => undefined,
      onDone: () => undefined,
    }),
  ).rejects.toMatchObject({ name: 'ApiError', code: 'stream_malformed_frame', status: 502 });
});

test('rejects a stream that ends without a completion event', async () => {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode('event: token\ndata: {"token":"Partial"}\n\n'));
      controller.close();
    },
  });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })));

  await expect(
    streamQuestion('conversation', 'question', {
      onMetadata: () => undefined,
      onToken: () => undefined,
      onDone: () => undefined,
    }),
  ).rejects.toMatchObject({ code: 'stream_incomplete', status: 502 });
});

test('preserves the server status on a typed stream error', async () => {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          'event: error\ndata: {"code":"internal_error","message":"Retry","status":500}\n\n',
        ),
      );
      controller.close();
    },
  });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })));

  await expect(
    streamQuestion('conversation', 'question', {
      onMetadata: () => undefined,
      onToken: () => undefined,
      onDone: () => undefined,
    }),
  ).rejects.toMatchObject({ code: 'internal_error', status: 500 });
});
