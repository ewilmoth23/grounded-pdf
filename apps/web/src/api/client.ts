import type {
  Conversation,
  ConversationDetail,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
  return (await response.json()) as T;
}

export const api = {
  documents: {
    list: () => request<DocumentRecord[]>('/documents'),
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
    list: () => request<Conversation[]>('/conversations'),
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
