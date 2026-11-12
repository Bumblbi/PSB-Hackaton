import {
  ArrowRight,
  ArrowUp,
  BookOpen,
  CalendarDays,
  Check,
  ChevronDown,
  CircleHelp,
  FileText,
  Menu,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, errorText } from './api';
import AnswerCard from './components/AnswerCard';
import DocumentLibrary from './components/DocumentLibrary';
import SourceViewer, { type SourceSelection } from './components/SourceViewer';
import { dateLabel, kinds } from './format';
import type {
  Chat,
  ChatSummary,
  Citation,
  DocumentInfo,
  Health,
  Kind,
  QuestionInput,
} from './types';

function currentRoute() {
  return window.location.hash.slice(1) || '/new';
}
function navigate(route: string) {
  window.location.hash = route;
}
const examples = [
  {
    label: 'Разобраться в условиях',
    text: 'Какой срок оплаты установлен по договору сопровождения?',
    detail: 'Обязательства и сроки',
  },
  {
    label: 'Учесть дату события',
    text: 'Как менялся срок оплаты по договору сопровождения с учётом допсоглашения?',
    detail: 'Редакции и изменения',
  },
  {
    label: 'Проверить порядок действий',
    text: 'Как направить претензию по договору сопровождения?',
    detail: 'Положения документа',
  },
];

export default function App() {
  const [route, setRoute] = useState(currentRoute);
  const [health, setHealth] = useState<Health | null>(null);
  const [connectionError, setConnectionError] = useState(false);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [chatTotal, setChatTotal] = useState(0);
  const [chatsError, setChatsError] = useState(false);
  const [chatsLoading, setChatsLoading] = useState(true);
  const [chat, setChat] = useState<Chat | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState('');
  const [draft, setDraft] = useState('');
  const [eventDate, setEventDate] = useState('');
  const [kind, setKind] = useState<Kind | ''>('');
  const [context, setContext] = useState<DocumentInfo | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [source, setSource] = useState<SourceSelection | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [historySearch, setHistorySearch] = useState('');
  const [helpOpen, setHelpOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState('');
  const [sendError, setSendError] = useState('');
  const [reload, setReload] = useState(0);
  const sendingRef = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const navigation = useRef<HTMLElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const sequence = useRef(0);
  const isLibrary = route === '/documents';
  const chatId = /^\/chat\/([a-zA-Z0-9-]+)$/.exec(route)?.[1] ?? null;
  const invalidRoute = route !== '/new' && !isLibrary && !chatId;

  const refreshChats = useCallback(async (offset = 0) => {
    setChatsLoading(true);
    try {
      const page = await api.chats(offset);
      setChats((previous) => (offset ? [...previous, ...page.items] : page.items));
      setChatTotal(page.total);
      setChatsError(false);
    } catch {
      setChatsError(true);
    } finally {
      setChatsLoading(false);
    }
  }, []);
  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
      setConnectionError(false);
    } catch {
      setConnectionError(true);
    }
  }, []);
  useEffect(() => {
    const update = () => {
      setRoute(currentRoute());
      setSidebarOpen(false);
    };
    window.addEventListener('hashchange', update);
    void refreshChats();
    void refreshHealth();
    const timer = window.setInterval(() => {
      if (window.document.visibilityState === 'visible') void refreshHealth();
    }, 30_000);
    return () => {
      window.removeEventListener('hashchange', update);
      window.clearInterval(timer);
    };
  }, [refreshChats, refreshHealth]);
  useEffect(() => {
    if (sendingRef.current) return;
    const controller = new AbortController();
    const version = ++sequence.current;
    setChat(null);
    setChatError('');
    setSendError('');
    setPending('');
    if (!chatId) {
      setChatLoading(false);
      return () => controller.abort();
    }
    setChatLoading(true);
    api
      .chat(chatId, controller.signal)
      .then((result) => {
        if (version === sequence.current && !controller.signal.aborted) setChat(result);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setChatError(errorText(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setChatLoading(false);
      });
    return () => controller.abort();
  }, [chatId, route, reload]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' });
  }, [chat?.messages.length, pending]);
  useEffect(() => {
    if (!sidebarOpen) return;
    const opener = window.document.activeElement as HTMLElement | null;
    const controls = () =>
      Array.from(
        navigation.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input') ?? [],
      );
    controls()[0]?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSidebarOpen(false);
        return;
      }
      if (event.key !== 'Tab') return;
      const items = controls();
      const first = items[0],
        last = items[items.length - 1];
      if (event.shiftKey && window.document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && window.document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    window.addEventListener('keydown', keydown);
    return () => {
      window.removeEventListener('keydown', keydown);
      opener?.focus();
    };
  }, [sidebarOpen]);
  useEffect(() => {
    const previous = window.document.title;
    window.document.title = `${isLibrary ? 'Документы' : chat?.title || 'Новый диалог'} · Юридический ассистент ПСБ`;
    return () => {
      window.document.title = previous;
    };
  }, [isLibrary, chat?.title]);

  function go(path: string) {
    if (sendingRef.current) return;
    setSource(null);
    setSidebarOpen(false);
    setHelpOpen(false);
    navigate(path);
  }
  function newChat() {
    if (sendingRef.current) return;
    setChat(null);
    setDraft('');
    setContext(null);
    setEventDate('');
    setKind('');
    setSendError('');
    setPending('');
    setFiltersOpen(false);
    setReload((n) => n + 1);
    go('/new');
    window.setTimeout(() => textarea.current?.focus(), 0);
  }
  function openCitation(citation: Citation) {
    setSource({ documentId: citation.document_id, versionId: citation.version_id, citation });
  }
  function useDocument(document: DocumentInfo) {
    if (sendingRef.current) return;
    setSource(null);
    go('/new');
    setChat(null);
    setContext(document);
    setKind('');
    setSendError('');
    window.setTimeout(() => textarea.current?.focus(), 0);
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || sendingRef.current || chatLoading || chatError || question.length > 8000)
      return;
    sendingRef.current = true;
    setSending(true);
    setSendError('');
    setPending(question);
    ++sequence.current;
    let targetId = chatId;
    try {
      if (!targetId) {
        targetId = (await api.createChat(question.slice(0, 200))).chat_id;
        navigate(`/chat/${targetId}`);
      }
      const body: QuestionInput = { question };
      if (eventDate) body.event_date = eventDate;
      if (context) body.document_id = context.document_id;
      if (kind) body.document_kind = kind;
      await api.send(targetId, body);
      const saved = await api.chat(targetId);
      setChat(saved);
      setDraft('');
      setPending('');
    } catch (error) {
      setSendError(errorText(error));
      setPending('');
      if (targetId) {
        try {
          setChat(await api.chat(targetId));
        } catch {
          /* Keep draft when server is unavailable. */
        }
      }
    } finally {
      sendingRef.current = false;
      setSending(false);
      setChatLoading(false);
      void refreshChats();
      void refreshHealth();
      window.setTimeout(() => textarea.current?.focus(), 0);
    }
  }
  const hasMessages = (chat?.messages.length ?? 0) > 0 || !!pending;
  const visibleChats = chats.filter((item) =>
    item.title.toLocaleLowerCase('ru').includes(historySearch.toLocaleLowerCase('ru')),
  );
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          window.document.getElementById('main-content')?.focus();
        }}
      >
        Перейти к содержимому
      </a>
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          aria-label="Закрыть навигацию"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        ref={navigation}
        className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}
        aria-label="Навигация"
        role={sidebarOpen ? 'dialog' : undefined}
        aria-modal={sidebarOpen ? true : undefined}
      >
        <div className="brand">
          <div className="brand-wordmark">
            ПСБ
            <span aria-hidden="true" className="brand-rule" />
          </div>
          <button
            className="icon-button mobile-menu-close"
            aria-label="Закрыть меню"
            onClick={() => setSidebarOpen(false)}
          >
            <X />
          </button>
          <span className="brand-description">Юридический ассистент</span>
        </div>
        <button className="new-chat-button" onClick={newChat} disabled={sending}>
          <Plus />
          Новый диалог
          <span className="new-chat-plus" aria-hidden="true">
            ↗
          </span>
        </button>
        <nav className="main-navigation">
          <button
            className={!isLibrary ? 'nav-item active' : 'nav-item'}
            onClick={() => go(chatId ? `/chat/${chatId}` : '/new')}
            disabled={sending}
            aria-current={!isLibrary ? 'page' : undefined}
          >
            <MessageSquare />
            Рабочее место
          </button>
          <button
            className={isLibrary ? 'nav-item active' : 'nav-item'}
            onClick={() => go('/documents')}
            disabled={sending}
            aria-current={isLibrary ? 'page' : undefined}
          >
            <BookOpen />
            Документы
            <ArrowRight className="nav-arrow" />
          </button>
        </nav>
        <div className="history-header">
          <h2>Диалоги</h2>
          <span>{chatTotal}</span>
        </div>
        <label className="history-search">
          <Search />
          <input
            aria-label="Поиск в загруженных диалогах"
            placeholder="Поиск в списке"
            value={historySearch}
            onChange={(e) => setHistorySearch(e.target.value)}
          />
        </label>
        <div className="history-list" aria-busy={chatsLoading}>
          {chatsError ? (
            <div className="sidebar-note">
              История недоступна
              <button onClick={() => void refreshChats()}>Повторить загрузку</button>
            </div>
          ) : visibleChats.length ? (
            visibleChats.map((item) => (
              <button
                key={item.chat_id}
                className={`history-item ${chatId === item.chat_id ? 'selected' : ''}`}
                disabled={sending}
                onClick={() => go(`/chat/${item.chat_id}`)}
                aria-current={chatId === item.chat_id ? 'page' : undefined}
              >
                <span>{item.title}</span>
                <small>{dateLabel(item.last_message_at || item.created_at)}</small>
              </button>
            ))
          ) : (
            <p className="sidebar-note">
              {chatsLoading
                ? 'Загружаем историю…'
                : historySearch
                  ? 'Совпадений нет'
                  : 'Ваши диалоги появятся здесь'}
            </p>
          )}
          {!chatsError && chats.length < chatTotal && (
            <button
              className="history-more"
              disabled={chatsLoading}
              onClick={() => void refreshChats(chats.length)}
            >
              {chatsLoading ? 'Загрузка…' : 'Загрузить ещё'}
            </button>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="scope-note">
            <ShieldCheck />
            <p>
              Ответы только по корпусу<span>С проверяемыми ссылками</span>
            </p>
          </div>
          <button
            className="sidebar-help"
            onClick={() => {
              setHelpOpen(true);
              setSidebarOpen(false);
            }}
          >
            <CircleHelp />
            Как работать с ассистентом
          </button>
          <div className="workspace-identity">
            <span className="identity-monogram">Ю</span>
            <div>
              Рабочее место юриста<span>Локальная версия</span>
            </div>
            <span className="identity-dot" aria-hidden="true" />
          </div>
        </div>
      </aside>
      <div className="workspace" inert={sidebarOpen}>
        <header className="workspace-header">
          <div className="header-breadcrumb">
            <button
              className="icon-button mobile-menu-button"
              aria-label="Открыть меню"
              aria-expanded={sidebarOpen}
              onClick={() => setSidebarOpen(true)}
            >
              <Menu />
            </button>
            <span>Юридическая работа</span>
            <span className="breadcrumb-divider">/</span>
            <strong>{isLibrary ? 'Документы' : 'Консультация'}</strong>
          </div>
          <button
            className={`connection-indicator ${connectionError ? 'connection-failed' : ''}`}
            onClick={() => {
              void refreshHealth();
              void refreshChats();
            }}
            aria-label={
              connectionError
                ? 'Соединение потеряно. Повторить подключение'
                : 'Проверить соединение'
            }
          >
            <span className="status-dot" />
            {connectionError
              ? 'Нет соединения'
              : health
                ? health.chunks > 0
                  ? 'Корпус подключён'
                  : 'Корпус пуст'
                : 'Подключаемся'}
            <RefreshCw />
          </button>
        </header>
        <main
          id="main-content"
          className={`main-content ${isLibrary ? 'library-main' : ''}`}
          tabIndex={-1}
        >
          {isLibrary ? (
            <DocumentLibrary
              onOpen={(document) =>
                setSource({ documentId: document.document_id, versionId: document.version_id })
              }
            />
          ) : invalidRoute ? (
            <div className="page-error">
              <h1>Страница не найдена</h1>
              <button className="primary-button" onClick={newChat}>
                Новый диалог
              </button>
            </div>
          ) : (
            <>
              <div className="conversation-heading">
                <div>
                  <span className="eyebrow">
                    {hasMessages ? 'Диалог по документам' : 'Рабочее место юриста'}
                  </span>
                  <h1>{chat?.title || 'Новый диалог'}</h1>
                </div>
                <button
                  className="quiet-button"
                  onClick={() => go('/documents')}
                  disabled={sending}
                >
                  <BookOpen />
                  Открыть корпус
                  <ArrowRight />
                </button>
              </div>
              {health?.llm_provider === 'disabled' && (
                <div className="provider-notice">
                  <InfoIcon />
                  <span>
                    Генерация ответов пока не подключена. Можно изучать документы и историю диалогов
                  </span>
                </div>
              )}
              <div
                className={`conversation-scroll ${!hasMessages ? 'conversation-empty' : ''}`}
                aria-busy={chatLoading}
              >
                {chatLoading ? (
                  <div className="conversation-loading" role="status">
                    Загружаем диалог…
                  </div>
                ) : chatError ? (
                  <div className="page-error" role="alert">
                    <h2>Диалог не загрузился</h2>
                    <p>{chatError}</p>
                    <button className="secondary-button" onClick={() => setReload((n) => n + 1)}>
                      Повторить загрузку
                    </button>
                  </div>
                ) : !hasMessages ? (
                  <div className="welcome">
                    <div className="welcome-symbol" aria-hidden="true">
                      §<span>[1]</span>
                    </div>
                    <span className="eyebrow">От вопроса — к основанию</span>
                    <h2>
                      Разберите правовой вопрос.
                      <br />
                      <span>Проверьте каждую ссылку.</span>
                    </h2>
                    <p>
                      Ассистент найдёт положения в документах, учтёт дату события и покажет, на чём
                      основан ответ
                    </p>
                    <div className="example-list">
                      {examples.map((example, i) => (
                        <button
                          className="example-row"
                          key={example.label}
                          onClick={() => {
                            setDraft(example.text);
                            if (i === 1) setFiltersOpen(true);
                            textarea.current?.focus();
                          }}
                        >
                          <span className="example-number">0{i + 1}</span>
                          <span>
                            <strong>{example.label}</strong>
                            <small>{example.detail}</small>
                          </span>
                          <ArrowUp className="example-arrow" />
                        </button>
                      ))}
                    </div>
                    <div className="welcome-footnote">
                      <FileText />
                      Основание важнее уверенного ответа
                    </div>
                  </div>
                ) : (
                  <div className="messages">
                    {chat?.messages.map((message) =>
                      message.role === 'assistant' ? (
                        message.answer ? (
                          <AnswerCard
                            key={message.message_id}
                            answer={message.answer}
                            onCitation={openCitation}
                          />
                        ) : (
                          <article className="assistant-message" key={message.message_id}>
                            <div className="message-byline">Юридический ассистент</div>
                            <p className="answer-text">{message.content}</p>
                          </article>
                        )
                      ) : (
                        <article className="user-message" key={message.message_id}>
                          <div className="user-byline">
                            Вы<span>{dateLabel(message.created_at)}</span>
                          </div>
                          <p>{message.content}</p>
                        </article>
                      ),
                    )}
                    {pending && (
                      <article className="user-message">
                        <div className="user-byline">Вы</div>
                        <p>{pending}</p>
                      </article>
                    )}
                    {sending && (
                      <div className="thinking" role="status">
                        <span className="thinking-mark">§</span>
                        <div>
                          Проверяем основания
                          <span>Поиск по корпусу, выбор редакций и проверка цитат</span>
                        </div>
                      </div>
                    )}
                    <div ref={end} />
                  </div>
                )}
              </div>
              <div className="composer-area">
                {sendError && (
                  <div className="inline-error send-error" role="alert">
                    <p>{sendError}</p>
                    <button className="quiet-button" onClick={() => setReload((n) => n + 1)}>
                      Обновить диалог
                    </button>
                  </div>
                )}
                <form className="composer" onSubmit={submit}>
                  {(context || eventDate || kind) && (
                    <div className="context-tags">
                      {context && (
                        <span>
                          <FileText />
                          {context.title}
                          <button
                            type="button"
                            aria-label="Убрать документ из контекста"
                            disabled={sending}
                            onClick={() => setContext(null)}
                          >
                            <X />
                          </button>
                        </span>
                      )}
                      {eventDate && (
                        <span>
                          <CalendarDays />
                          {dateLabel(eventDate)}
                          <button
                            type="button"
                            aria-label="Убрать дату события"
                            disabled={sending}
                            onClick={() => setEventDate('')}
                          >
                            <X />
                          </button>
                        </span>
                      )}
                      {kind && (
                        <span>
                          {kinds[kind]}
                          <button
                            type="button"
                            aria-label="Убрать тип документа"
                            disabled={sending}
                            onClick={() => setKind('')}
                          >
                            <X />
                          </button>
                        </span>
                      )}
                    </div>
                  )}
                  <label className="sr-only" htmlFor="question">
                    Юридический вопрос
                  </label>
                  <textarea
                    id="question"
                    ref={textarea}
                    placeholder="Опишите вопрос, договор или ситуацию…"
                    value={draft}
                    maxLength={8000}
                    rows={3}
                    disabled={sending || !!chatError || chatLoading}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(event) => {
                      if (
                        event.key === 'Enter' &&
                        !event.shiftKey &&
                        !event.nativeEvent.isComposing &&
                        !window.matchMedia('(pointer: coarse)').matches
                      ) {
                        event.preventDefault();
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                    aria-describedby="composer-help"
                  />
                  {filtersOpen && (
                    <div className="composer-filters">
                      <label>
                        <span>Дата события</span>
                        <input
                          type="date"
                          value={eventDate}
                          disabled={sending}
                          onChange={(e) => setEventDate(e.target.value)}
                        />
                      </label>
                      <label>
                        <span>Тип документа</span>
                        <select
                          aria-label="Тип документа"
                          value={kind}
                          disabled={sending || !!context}
                          onChange={(e) => setKind(e.target.value as Kind | '')}
                        >
                          <option value="">Все документы</option>
                          {Object.entries(kinds).map(([key, label]) => (
                            <option key={key} value={key}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <p>Дата помогает выбрать применимую редакцию</p>
                    </div>
                  )}
                  <div className="composer-bottom">
                    <button
                      type="button"
                      className={`quiet-button context-toggle ${filtersOpen ? 'is-open' : ''}`}
                      aria-expanded={filtersOpen}
                      disabled={sending}
                      onClick={() => setFiltersOpen((value) => !value)}
                    >
                      <SlidersHorizontal />
                      Уточнить контекст
                      <ChevronDown />
                    </button>
                    <div className="composer-actions">
                      <span className="character-count" aria-live="off">
                        {draft.length > 7000 ? (
                          `${draft.length} / 8000`
                        ) : (
                          <>
                            <kbd>Enter</kbd> отправить
                          </>
                        )}
                      </span>
                      <button
                        type="submit"
                        className="send-button"
                        aria-label="Отправить вопрос"
                        disabled={!draft.trim() || sending || !!chatError || chatLoading}
                      >
                        <ArrowUp />
                      </button>
                    </div>
                  </div>
                </form>
                <div className="composer-caption" id="composer-help">
                  <ShieldCheck />
                  <span>Ассистент может ошибаться. Проверяйте выводы по источникам</span>
                  <span className="line-break-hint">Shift + Enter — новая строка</span>
                </div>
              </div>
            </>
          )}
        </main>
      </div>
      {source && (
        <SourceViewer
          key={`${source.documentId}:${source.versionId}:${source.citation?.chunk_id || ''}`}
          source={source}
          onClose={() => setSource(null)}
          onUse={useDocument}
        />
      )}
      {helpOpen && <Help onClose={() => setHelpOpen(false)} />}
    </div>
  );
}

function InfoIcon() {
  return <CircleHelp aria-hidden="true" />;
}
function Help({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const element = ref.current;
    opener.current ??= window.document.activeElement as HTMLElement | null;
    element?.showModal();
    return () => {
      element?.close();
      if (opener.current?.isConnected) opener.current.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="help-dialog"
      aria-labelledby="help-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div>
        <header>
          <h2 id="help-title">От вопроса к проверенному основанию</h2>
          <button className="icon-button" aria-label="Закрыть справку" onClick={onClose}>
            <X />
          </button>
        </header>
        <ol>
          <li>
            <strong>Опишите ситуацию</strong>
            <p>
              Укажите предмет вопроса и документ. Если важен период, добавьте дату события в
              контекст
            </p>
          </li>
          <li>
            <strong>Оцените полноту ответа</strong>
            <p>
              Проверьте статус. Если не хватает данных, ассистент перечислит пробелы или попросит
              уточнение
            </p>
          </li>
          <li>
            <strong>Откройте основание</strong>
            <p>
              Нажмите [1] или строку источника. Откроется конкретная редакция с выделенной цитатой
            </p>
          </li>
        </ol>
        <p className="help-note">
          Ответы строятся по загруженному корпусу. Доступность документа в корпусе сама по себе не
          подтверждает его применимость к вашей ситуации
        </p>
        <button className="primary-button" onClick={onClose}>
          <Check />
          Понятно
        </button>
      </div>
    </dialog>
  );
}
