import type {
  Conversation,
  ConversationDetail,
  DocumentDetail,
  DocumentRecord,
  SafeSettings,
  SearchResult,
  UploadResult,
  Verification,
} from '../types/api';

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? 'http://localhost:8000/api/v1';

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

interface LooseErrorPayload {
  error?: { message?: unknown; code?: unknown };
  detail?: unknown;
}

/** Extracts a readable message from any JSON error body, including FastAPI 422 shapes. */
export function toApiError(payload: unknown, status: number): ApiError {
  const fallback = `Request failed (${status})`;
  const loose = (payload ?? {}) as LooseErrorPayload;
  const message = loose.error?.message;
  const code = loose.error?.code;
  if (typeof message === 'string' && message) {
    return new ApiError(message, typeof code === 'string' && code ? code : 'api_error', status);
  }
  const detail = loose.detail;
  if (typeof detail === 'string' && detail) {
    return new ApiError(detail, 'validation_error', status);
  }
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: unknown } | undefined;
    if (first && typeof first.msg === 'string' && first.msg) {
      return new ApiError(first.msg, 'validation_error', status);
    }
  }
  return new ApiError(fallback, 'api_error', status);
}

async function requestWithHeaders<T>(
  path: string,
  init?: RequestInit,
): Promise<{ data: T; headers: Headers }> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new ApiError(
        'The server returned an unreadable response',
        'invalid_response',
        response.status,
      );
    }
    throw toApiError(payload, response.status);
  }
  return { data: (await response.json()) as T, headers: response.headers };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await requestWithHeaders<T>(path, init)).data;
}

/** Largest page the list endpoints accept. */
const LIST_PAGE_SIZE = 500;
/** Safety cap so a bad total count can never loop forever. */
const LIST_MAX_PAGES = 10;

/**
 * Fetch every page of a paginated list endpoint (the server caps `limit` at
 * 500), following the `X-Total-Count` response header until all rows arrived.
 */
async function requestAllPages<T>(path: string): Promise<T[]> {
  const items: T[] = [];
  for (let page = 0; page < LIST_MAX_PAGES; page += 1) {
    const { data, headers } = await requestWithHeaders<T[]>(
      `${path}?limit=${LIST_PAGE_SIZE}&offset=${page * LIST_PAGE_SIZE}`,
    );
    items.push(...data);
    const totalHeader = headers.get('X-Total-Count');
    const total = totalHeader === null ? Number.NaN : Number(totalHeader);
    const complete = Number.isFinite(total) ? items.length >= total : data.length < LIST_PAGE_SIZE;
    if (complete || data.length === 0) break;
  }
  return items;
}

export const api = {
  documents: {
    list: () => requestAllPages<DocumentRecord>('/documents'),
    get: (id: string) => request<DocumentDetail>(`/documents/${id}`),
    reprocessStale: () =>
      request<{ queued: number; remaining: number }>('/documents/reprocess-stale', {
        method: 'POST',
      }),
    upload: (files: File[]) => {
      const body = new FormData();
      files.forEach((file) => body.append('files', file));
      return request<UploadResult>('/documents', { method: 'POST', body });
    },
    retry: (id: string) => request<DocumentRecord>(`/documents/${id}/retry`, { method: 'POST' }),
    delete: (id: string) => request<{ deleted: boolean }>(`/documents/${id}`, { method: 'DELETE' }),
    fileUrl: (id: string) => `${API_BASE}/documents/${id}/file`,
  },
  conversations: {
    list: () => requestAllPages<Conversation>('/conversations'),
    get: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
    create: (documentIds: string[] = []) =>
      request<Conversation>('/conversations', {
        method: 'POST',
        body: JSON.stringify({ title: 'New conversation', document_ids: documentIds }),
      }),
    rename: (id: string, title: string) =>
      request<Conversation>(`/conversations/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      }),
    selectDocuments: (id: string, documentIds: string[]) =>
      request<Conversation>(`/conversations/${id}/documents`, {
        method: 'PUT',
        body: JSON.stringify({ document_ids: documentIds }),
      }),
    delete: (id: string) =>
      request<{ deleted: boolean }>(`/conversations/${id}`, { method: 'DELETE' }),
    verify: (id: string, messageId: string) =>
      request<Verification>(`/conversations/${id}/messages/${messageId}/verify`),
    exportUrl: (id: string, format: 'markdown' | 'html') =>
      `${API_BASE}/conversations/${id}/export?format=${format}`,
  },
  search: {
    query: (q: string, documentIds: string[] = []) => {
      const params = new URLSearchParams({ q });
      documentIds.forEach((id) => params.append('document_ids', id));
      return request<SearchResult>(`/search?${params.toString()}`);
    },
  },
  settings: {
    get: () => request<SafeSettings>('/settings'),
    update: (values: Partial<SafeSettings>) =>
      request<SafeSettings>('/settings', { method: 'PATCH', body: JSON.stringify(values) }),
  },
};
