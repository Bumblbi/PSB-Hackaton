import { ArrowUpRight, FileText, Search, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, errorText } from '../api';
import { kinds, validity } from '../format';
import type { DocumentInfo, Kind } from '../types';

export default function DocumentLibrary({ onOpen }: { onOpen: (document: DocumentInfo) => void }) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<Kind | ''>('');
  const [items, setItems] = useState<DocumentInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [offset, setOffset] = useState(0);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    const timer = window.setTimeout(() => {
      api
        .documents(query, kind, offset, controller.signal)
        .then((page) => {
          if (!controller.signal.aborted) {
            setItems((prev) => (offset ? [...prev, ...page.items] : page.items));
            setTotal(page.total);
          }
        })
        .catch((err) => {
          if (!controller.signal.aborted) setError(errorText(err));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 200);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, kind, offset, retry]);
  return (
    <div className="library-page">
      <div className="page-intro">
        <span className="eyebrow">Корпус знаний</span>
        <h1>Документы и редакции</h1>
        <p>Проверьте источник целиком, прежде чем опираться на вывод</p>
      </div>
      <div className="library-toolbar">
        <label className="search-field">
          <Search aria-hidden="true" />
          <input
            aria-label="Поиск документов"
            placeholder="Название документа"
            value={query}
            maxLength={200}
            onChange={(e) => {
              setQuery(e.target.value);
              setOffset(0);
            }}
          />
          {query && (
            <button
              className="icon-button"
              aria-label="Очистить поиск"
              onClick={() => {
                setQuery('');
                setOffset(0);
              }}
            >
              <X />
            </button>
          )}
        </label>
        <label className="kind-filter">
          <span className="sr-only">Тип документа</span>
          <select
            aria-label="Тип документа"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as Kind | '');
              setOffset(0);
            }}
          >
            <option value="">Все типы</option>
            {Object.entries(kinds).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="library-meta" role="status">
        {loading
          ? 'Ищем документы…'
          : error
            ? 'Не удалось загрузить корпус'
            : `Редакций найдено: ${total}`}
      </div>
      {error ? (
        <div className="inline-error" role="alert">
          <p>{error}</p>
          <button className="quiet-button" onClick={() => setRetry((n) => n + 1)}>
            Повторить загрузку
          </button>
        </div>
      ) : (
        <div className="document-list" aria-busy={loading}>
          {items.map((doc) => (
            <button className="document-row" key={doc.version_id} onClick={() => onOpen(doc)}>
              <span className="file-icon">
                <FileText aria-hidden="true" />
              </span>
              <span className="document-row-body">
                <span className="document-row-meta">
                  {kinds[doc.kind]}
                  <span>Редакция {doc.revision}</span>
                </span>
                <span className="document-row-title">{doc.title}</span>
                <span className="document-row-validity">
                  {validity(doc.valid_from, doc.valid_to)}
                </span>
              </span>
              <ArrowUpRight aria-hidden="true" />
            </button>
          ))}
          {!loading && items.length === 0 && (
            <div className="library-empty">
              <FileText aria-hidden="true" />
              <h2>{query || kind ? 'Документы не найдены' : 'В корпусе пока нет документов'}</h2>
              <p>
                {query || kind
                  ? 'Попробуйте другое название или измените тип документа'
                  : 'После загрузки корпуса здесь появятся документы и доступные редакции'}
              </p>
              {(query || kind) && (
                <button
                  className="secondary-button"
                  onClick={() => {
                    setQuery('');
                    setKind('');
                    setOffset(0);
                  }}
                >
                  Сбросить фильтры
                </button>
              )}
            </div>
          )}
          {items.length < total && (
            <button
              disabled={loading}
              className="secondary-button load-more"
              onClick={() => setOffset(items.length)}
            >
              {loading ? 'Загрузка…' : 'Показать ещё'}
            </button>
          )}
        </div>
      )}
      <p className="library-note">
        Здесь показаны редакции активного корпуса. Источники из прежних ответов доступны по их
        ссылкам
      </p>
    </div>
  );
}
