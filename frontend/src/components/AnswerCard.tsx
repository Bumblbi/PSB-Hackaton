import { Check, CheckCheck, Copy, FileText, Info } from 'lucide-react';
import { useState } from 'react';
import { statuses } from '../format';
import type { Answer, Citation } from '../types';

export function AnswerText({
  text,
  citations,
  onCitation,
}: {
  text: string;
  citations: Citation[];
  onCitation: (citation: Citation) => void;
}) {
  return (
    <div className="answer-text">
      {text.split(/(\[\d+\])/g).map((part, index) => {
        const ref = /^\[(\d+)\]$/.exec(part);
        const citation = ref && citations.find((item) => item.ref === Number(ref[1]));
        return citation ? (
          <button
            key={index}
            className="inline-cite"
            onClick={() => onCitation(citation)}
            aria-label={`Открыть источник ${citation.ref}`}
          >
            [{citation.ref}]
          </button>
        ) : (
          <span key={index}>{part}</span>
        );
      })}
    </div>
  );
}

export default function AnswerCard({
  answer,
  onCitation,
}: {
  answer: Answer;
  onCitation: (citation: Citation) => void;
}) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const state = statuses[answer.status] ?? { label: 'Результат проверки', tone: 'neutral' };
  async function copy() {
    try {
      const sources = answer.citations
        .map(
          (c) =>
            `[${c.ref}] ${c.locator}\n${c.quote}\nДокумент: ${c.document_id}, редакция: ${c.version_id}`,
        )
        .join('\n\n');
      await navigator.clipboard.writeText(
        [answer.answer, answer.reason, ...answer.missing_info, answer.clarifying_question, sources]
          .filter(Boolean)
          .join('\n\n'),
      );
      setCopied(true);
      setCopyError(false);
    } catch {
      setCopyError(true);
    }
  }
  return (
    <article className="assistant-message" aria-label="Ответ ассистента">
      <div className="message-byline">
        <span className="assistant-mark" aria-hidden="true">
          §
        </span>
        <span>Юридический ассистент</span>
        <span className={`answer-status ${state.tone}`}>
          {state.tone === 'success' ? <Check aria-hidden="true" /> : <Info aria-hidden="true" />}
          {state.label}
        </span>
      </div>
      {answer.answer && (
        <AnswerText text={answer.answer} citations={answer.citations} onCitation={onCitation} />
      )}
      {answer.reason && answer.reason !== answer.answer && (
        <p className="answer-reason">{answer.reason}</p>
      )}
      {answer.missing_info.length > 0 && (
        <section className="missing-info">
          <h3>Что нужно для ответа</h3>
          <ul>
            {answer.missing_info.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      )}
      {answer.clarifying_question && <p className="clarification">{answer.clarifying_question}</p>}
      {answer.citations.length > 0 && (
        <section className="evidence-list" aria-label="Основания ответа">
          <div className="evidence-heading">
            Основания ответа <span>{answer.citations.length}</span>
          </div>
          {answer.citations.map((cite, i) => (
            <button
              className="evidence-row"
              key={`${cite.ref}-${i}`}
              onClick={() => onCitation(cite)}
              aria-label={`Проверить основание ${cite.ref}`}
            >
              <span className="cite-number">{String(cite.ref).padStart(2, '0')}</span>
              <span className="evidence-description">
                <span className="evidence-locator">
                  <FileText aria-hidden="true" />
                  {cite.locator}
                </span>
                <span className="evidence-excerpt">{cite.quote}</span>
              </span>
              <span className="evidence-arrow" aria-hidden="true">
                ↗
              </span>
            </button>
          ))}
        </section>
      )}
      <div className="answer-footer">
        <button className="quiet-button" onClick={copy}>
          {copied ? <CheckCheck aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {copied ? 'Скопировано с источниками' : 'Копировать ответ'}
        </button>
        <span className="answer-timing">
          {Number.isFinite(answer.timings_ms.total)
            ? `${(answer.timings_ms.total / 1000).toFixed(1).replace('.', ',')} с`
            : ''}
        </span>
      </div>
      {copyError && (
        <p role="status" className="small-error">
          Не удалось скопировать. Выделите текст ответа вручную
        </p>
      )}
    </article>
  );
}
