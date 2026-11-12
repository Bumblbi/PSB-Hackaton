import { describe, expect, it } from 'vitest';
import { quoteRange, validity } from './format';

describe('source offsets', () => {
  it('finds literal quotes without interpreting markup', () => {
    const text = 'Статья: <script>unsafe</script> и оплата';
    const range = quoteRange(text, '<script>unsafe</script>')!;
    expect(text.slice(...range)).toBe('<script>unsafe</script>');
  });
  it('maps normalized whitespace back to the exact source', () => {
    const text = 'Срок\n  оплаты — 10\u00a0рабочих дней.';
    const range = quoteRange(text, 'Срок оплаты — 10 рабочих дней')!;
    expect(text.slice(...range)).toBe('Срок\n  оплаты — 10\u00a0рабочих дней');
  });
  it('does not invent a match when the quote is absent', () => {
    expect(quoteRange('10 дней', '15 дней')).toBeNull();
    expect(quoteRange('10 дней', '   ')).toBeNull();
    expect(quoteRange('10 дней', '')).toBeNull();
  });
  it('does not imply an unlimited validity interval', () => {
    expect(validity('2024-01-01', null)).toContain('окончание не указано');
    expect(validity(null, null)).toContain('не указан');
    expect(validity('2024-01-01', '2025-01-01')).toContain('не включая');
  });
});
