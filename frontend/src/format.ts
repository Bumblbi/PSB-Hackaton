import type { AnswerStatus, Kind } from './types';

export const kinds: Record<Kind, string> = {
  law: 'Нормативный акт',
  contract: 'Договор',
  internal: 'Внутренний документ',
  amendment: 'Допсоглашение',
};
export const statuses: Record<AnswerStatus, { label: string; tone: string }> = {
  ANSWERED: { label: 'Ответ с основаниями', tone: 'success' },
  PARTIAL: { label: 'Частичный ответ', tone: 'warning' },
  INSUFFICIENT_EVIDENCE: { label: 'Недостаточно оснований', tone: 'warning' },
  NEED_CLARIFICATION: { label: 'Нужно уточнение', tone: 'neutral' },
  FALSE_PREMISE: { label: 'Предпосылка не подтверждена', tone: 'warning' },
  HISTORICAL_LAW_UNAVAILABLE: { label: 'Нет редакции на эту дату', tone: 'warning' },
  OUT_OF_SCOPE: { label: 'Вне области работы', tone: 'neutral' },
  DISALLOWED: { label: 'Запрос отклонён', tone: 'warning' },
  IGNORE_INJECTION: { label: 'Результат проверки запроса', tone: 'neutral' },
};
export function dateLabel(value: string | null | undefined) {
  if (!value) return 'Не указана';
  const date = new Date(
    value.length === 10
      ? `${value}T00:00:00`
      : /Z$|[+-]\d\d:\d\d$/.test(value)
        ? value
        : `${value}Z`,
  );
  return Number.isNaN(date.getTime())
    ? 'Не указана'
    : new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' }).format(
        date,
      );
}
export function validity(from: string | null, to: string | null) {
  if (!from) return 'Период действия не указан';
  return `С ${dateLabel(from)}${to ? ` до ${dateLabel(to)} (не включая)` : ' · окончание не указано'}`;
}

// Keep source offsets, including whitespace, while rendering untrusted text as text nodes.
export function quoteRange(text: string, quote: string): [number, number] | null {
  if (!quote) return null;
  const exact = text.indexOf(quote);
  if (exact >= 0) return [exact, exact + quote.length];
  const positions: number[] = [];
  let normalized = '';
  for (let i = 0; i < text.length; i++) {
    if (/\s/.test(text[i])) {
      if (normalized && !normalized.endsWith(' ')) {
        normalized += ' ';
        positions.push(i);
      }
    } else {
      normalized += text[i];
      positions.push(i);
    }
  }
  const target = quote.replace(/\s+/g, ' ').trim();
  if (!target) return null;
  const start = normalized.indexOf(target);
  return start < 0 ? null : [positions[start], positions[start + target.length - 1] + 1];
}
