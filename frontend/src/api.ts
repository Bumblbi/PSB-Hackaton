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
} from './types';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
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
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const message =
        typeof body?.detail === 'string' ? body.detail : 'Не удалось выполнить запрос';
      throw new ApiError(response.status, message);
    }
    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener('abort', onAbort);
  }
}

export const api = {
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
    if (error.status === 503)
      return error.message.includes('LLM')
        ? 'Модель сейчас недоступна. Вопрос сохранён в поле ввода — его можно отправить позже.'
        : 'Хранилище сейчас недоступно. Попробуйте обновить соединение.';
    if (error.status === 404) return 'Диалог или документ не найден. Возможно, ссылка устарела.';
    if (error.status === 422) return 'Проверьте вопрос, дату события и выбранный документ.';
    return 'Не удалось выполнить запрос. Попробуйте ещё раз.';
  }
  return 'Нет соединения с сервером. Проверьте подключение. Перед повторной отправкой обновите диалог: ответ мог сохраниться.';
}
