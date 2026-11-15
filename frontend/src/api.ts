import type {
  Answer,
  Chat,
  ChatSummary,
  DocumentInfo,
  Health,
  Kind,
  Page,
  QuestionInput,
  SourceDocument,
  UserSession,
} from './types';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public errors: { field: string; message: string }[] = [],
  ) {
    super(message);
  }
}

let csrfToken = '';
export function setCsrfToken(value: string) {
  csrfToken = value;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  options.signal?.addEventListener('abort', onAbort, { once: true });
  if (options.signal?.aborted) controller.abort();
  const timeout = window.setTimeout(() => controller.abort(), 180_000);
  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'legal-workspace',
        ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
        ...options.headers,
      },
    });
    if (!response.ok) {
      if (response.status === 401 && !path.startsWith('/api/v1/auth/')) {
        csrfToken = '';
        window.dispatchEvent(new Event('auth-expired'));
      }
      const body = await response.json().catch(() => null);
      const message =
        typeof body?.detail === 'string' ? body.detail : 'Не удалось выполнить запрос';
      const errors = Array.isArray(body?.errors)
        ? body.errors.filter(
            (item: unknown): item is { field: string; message: string } =>
              typeof item === 'object' &&
              item !== null &&
              'field' in item &&
              typeof item.field === 'string' &&
              'message' in item &&
              typeof item.message === 'string',
          )
        : [];
      throw new ApiError(response.status, message, errors);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener('abort', onAbort);
  }
}

export const api = {
  session: (signal?: AbortSignal) => request<UserSession>('/api/v1/auth/session', { signal }),
  login: (email: string, password: string) =>
    request<UserSession>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  register: (name: string, email: string, password: string) =>
    request<UserSession>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ name, email, password }),
    }),
  logout: () => request<void>('/api/v1/auth/logout', { method: 'POST' }),
  changePassword: (current_password: string, new_password: string) =>
    request<void>('/api/v1/auth/password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),
  health: (signal?: AbortSignal) => request<Health>('/health', { signal }),
  chats: (offset = 0, signal?: AbortSignal) =>
    request<Page<ChatSummary>>(`/api/v1/chats?limit=50&offset=${offset}`, { signal }),
  chat: (id: string, signal?: AbortSignal) =>
    request<Chat>(`/api/v1/chats/${encodeURIComponent(id)}`, { signal }),
  createChat: (title: string) =>
    request<{ chat_id: string }>('/api/v1/chats', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  send: (id: string, body: QuestionInput) =>
    request<Answer>(`/api/v1/chats/${encodeURIComponent(id)}/messages`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  documents: (q = '', kind: Kind | '' = '', offset = 0, signal?: AbortSignal) => {
    const query = new URLSearchParams({ q, offset: String(offset), limit: '50' });
    if (kind) query.set('kind', kind);
    return request<Page<DocumentInfo>>(`/api/v1/documents?${query}`, { signal });
  },
  document: (id: string, versionId: string, signal?: AbortSignal) =>
    request<SourceDocument>(
      `/api/v1/documents/${encodeURIComponent(id)}?version_id=${encodeURIComponent(versionId)}`,
      { signal },
    ),
};

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.errors.length && error.status !== 401) {
      return [...new Set(error.errors.map((item) => item.message))].join('\n');
    }
    if ([400, 401, 403, 409, 429].includes(error.status)) return error.message;
    if (error.status === 503)
      return error.message.includes('LLM')
        ? 'Модель сейчас недоступна. Вопрос сохранён в поле ввода — его можно отправить позже.'
        : 'Хранилище сейчас недоступно. Попробуйте обновить соединение.';
    if (error.status === 404) return 'Диалог или документ не найден. Возможно, ссылка устарела.';
    if (error.status === 422) return error.message;
    return 'Не удалось выполнить запрос. Попробуйте ещё раз.';
  }
  return 'Нет соединения с сервером. Проверьте подключение. Перед повторной отправкой обновите диалог: ответ мог сохраниться.';
}
