import { ArrowLeft, ArrowUpRight, BookOpen, FileText, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api, errorText } from '../api';
import { kinds, quoteRange, validity } from '../format';
import type { Citation, DocumentInfo, SourceDocument } from '../types';

export type SourceSelection = { documentId: string; versionId: string; citation?: Citation };

export function Highlight({ text, quote }: { text: string; quote: string }) {
  const range = quoteRange(text, quote);
  return range ? (
    <>
      {text.slice(0, range[0])}
      <mark>{text.slice(range[0], range[1])}</mark>
      {text.slice(range[1])}
    </>
  ) : (
    <>{text}</>
  );
}

export default function SourceViewer({
  source,
  onClose,
  onUse,
}: {
  source: SourceSelection;
  onClose: () => void;
  onUse: (document: DocumentInfo) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const selected = useRef<HTMLElement>(null);
  const [document, setDocument] = useState<SourceDocument | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [tab, setTab] = useState<'document' | 'quote'>('document');
  useEffect(() => {
    const element = dialog.current;
    opener.current ??= window.document.activeElement as HTMLElement | null;
    element?.showModal();
    return () => {
      element?.close();
      if (opener.current?.isConnected) opener.current.focus();
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setDocument(null);
    setError('');
    api
      .document(source.documentId, source.versionId, controller.signal)
      .then(setDocument)
      .catch((err) => {
        if (!controller.signal.aborted) setError(errorText(err));
      });
    return () => controller.abort();
  }, [source.documentId, source.versionId, retry]);
  useEffect(() => {
    if (document) selected.current?.scrollIntoView({ block: 'center' });
  }, [document, tab]);
  const selectedSection = document?.sections.find(
    (section) => section.chunk_id === source.citation?.chunk_id,
  );
  const verified =
    source.citation && selectedSection && quoteRange(selectedSection.text, source.citation.quote);
  return (
    <dialog
      ref={dialog}
      className="source-dialog"
      aria-labelledby="source-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
    >
      <div className="source-inner">
        <header className="source-header">
          <div>
            <span className="eyebrow">Проверка основания</span>
            <h2 id="source-title">
              {source.citation ? `Источник [${source.citation.ref}]` : 'Просмотр документа'}
            </h2>
          </div>
          <button className="icon-button" aria-label="Закрыть документ" onClick={onClose}>
            <X />
          </button>
        </header>
        {error ? (
          <div className="panel-error" role="alert">
            <BookOpen />
            <h3>Документ не загрузился</h3>
            <p>{error}</p>
            <button className="secondary-button" onClick={() => setRetry((n) => n + 1)}>
              Попробовать снова
            </button>
          </div>
        ) : !document ? (
          <div className="panel-loading" role="status">
            Загружаем редакцию документа…
          </div>
        ) : (
          <>
            <div className="source-metadata">
              <span className="document-kind">
                <FileText />
                {kinds[document.version.kind]}
              </span>
              <h3>{document.title}</h3>
              <p>{validity(document.version.valid_from, document.version.valid_to)}</p>
              <div className="source-file">
                <span>{document.version.source_name}</span>
                <span>Редакция {document.version.revision}</span>
              </div>
              {document.version.is_current_only && (
                <p className="source-caution">В корпусе доступна только эта редакция закона</p>
              )}
            </div>
            {source.citation && (
              <div className="source-tabs" role="tablist" aria-label="Содержимое источника">
                <button
                  id="document-tab"
                  role="tab"
                  aria-selected={tab === 'document'}
                  aria-controls="source-content"
                  onClick={() => setTab('document')}
                >
                  В документе
                </button>
                <button
                  id="quote-tab"
                  role="tab"
                  aria-selected={tab === 'quote'}
                  aria-controls="source-content"
                  onClick={() => setTab('quote')}
                >
                  Только фрагмент
                </button>
              </div>
            )}
            <div
              id="source-content"
              className="source-content"
              role={source.citation ? 'tabpanel' : undefined}
              aria-labelledby={source.citation ? `${tab}-tab` : undefined}
              tabIndex={0}
            >
              {source.citation && !verified && (
                <p className="source-caution">
                  Не удалось точно сопоставить цитату с фрагментом этой редакции. Проверьте текст
                  документа
                </p>
              )}
              {(tab === 'quote' && source.citation
                ? document.sections.filter(
                    (section) => section.chunk_id === source.citation?.chunk_id,
                  )
                : document.sections
              ).map((section) => (
                <section
                  ref={section.chunk_id === source.citation?.chunk_id ? selected : undefined}
                  className={`source-section ${section.chunk_id === source.citation?.chunk_id ? 'selected-section' : ''}`}
                  key={section.chunk_id}
                >
                  <div className="section-locator">
                    {section.chunk_id === source.citation?.chunk_id && (
                      <span className="source-reference">[{source.citation.ref}]</span>
                    )}
                    {section.locator}
                  </div>
                  <p>
                    {section.chunk_id === source.citation?.chunk_id ? (
                      <Highlight text={section.text} quote={source.citation.quote} />
                    ) : (
                      section.text
                    )}
                  </p>
                </section>
              ))}
            </div>
            <footer className="source-footer">
              <span>Вывод следует проверить юристу</span>
              <button
                className="secondary-button"
                onClick={() =>
                  onUse({ ...document.version, chunk_count: document.sections.length })
                }
              >
                Вопрос по документу
                <ArrowUpRight />
              </button>
            </footer>
          </>
        )}
        <button className="source-mobile-close quiet-button" onClick={onClose}>
          <ArrowLeft />
          Вернуться к рабочему месту
        </button>
      </div>
    </dialog>
  );
}
