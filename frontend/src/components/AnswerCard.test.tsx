import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AnswerCard, { AnswerText } from './AnswerCard';
import { Highlight } from './SourceViewer';
import { statuses } from '../format';
import type { Answer, AnswerStatus, Citation } from '../types';

const citation: Citation = {
  ref: 1,
  document_id: 'doc',
  version_id: 'version',
  chunk_id: 'chunk',
  locator: 'Пункт 1.1',
  quote: '10 дней',
};
function answer(status: AnswerStatus): Answer {
  return {
    message_id: 'message',
    status,
    answer: 'Срок — 10 дней [1]',
    citations: [citation],
    reason: 'Основание из корпуса',
    missing_info: ['Дата события'],
    clarifying_question: 'На какую дату?',
    trace_id: 'trace',
    timings_ms: { total: 300 },
  };
}
describe('answer evidence', () => {
  it.each(Object.keys(statuses) as AnswerStatus[])('explains %s', (status) => {
    render(<AnswerCard answer={answer(status)} onCitation={vi.fn()} />);
    expect(screen.getByText(statuses[status].label)).toBeVisible();
    expect(screen.getByText('Дата события')).toBeVisible();
    expect(screen.getByText('На какую дату?')).toBeVisible();
  });
  it('opens only existing numbered citations', () => {
    const open = vi.fn();
    render(
      <AnswerText
        text="Источник [1], отсутствующий [9]"
        citations={[citation]}
        onCitation={open}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Открыть источник 1' }));
    expect(open).toHaveBeenCalledWith(citation);
    expect(screen.queryByRole('button', { name: 'Открыть источник 9' })).toBeNull();
  });
  it('renders document markup as inert text', () => {
    const { container } = render(
      <Highlight text={'<img src=x onerror="alert(1)"> 10 дней'} quote="10 дней" />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('mark')).toHaveTextContent('10 дней');
  });
  it('does not highlight a fabricated quote', () => {
    const { container } = render(<Highlight text="10 дней" quote="15 дней" />);
    expect(container.querySelector('mark')).toBeNull();
  });
});
