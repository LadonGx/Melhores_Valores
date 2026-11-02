import { describe, expect, it } from 'vitest';
import { formatDayLabel, formatRelative } from './formatNextCheck';

const now = new Date(2026, 10, 1, 20, 45); // 01/11/2026 20:45 (horário local)

describe('formatDayLabel', () => {
  it('hoje, amanhã e data', () => {
    expect(formatDayLabel(new Date(2026, 10, 1, 21, 0), now)).toBe('Hoje');
    expect(formatDayLabel(new Date(2026, 10, 2, 3, 0), now)).toBe('Amanhã');
    expect(formatDayLabel(new Date(2026, 10, 5, 3, 0), now)).toBe('05/11');
  });
});

describe('formatRelative', () => {
  it('minutos, horas e instantes', () => {
    expect(formatRelative(new Date(2026, 10, 1, 21, 0), now)).toBe('em 15 min');
    expect(formatRelative(new Date(2026, 10, 1, 22, 57), now)).toBe('em 2h 12min');
    expect(formatRelative(new Date(2026, 10, 2, 2, 45), now)).toBe('em 6h');
    expect(formatRelative(new Date(2026, 10, 1, 20, 45, 30), now)).toBe('em instantes');
    expect(formatRelative(new Date(2026, 10, 1, 20, 40), now)).toBe('em instantes');
  });
});
