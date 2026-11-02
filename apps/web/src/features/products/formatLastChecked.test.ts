import { describe, it, expect } from 'vitest';
import { formatLastChecked, isStale } from './formatLastChecked';

// Horário local (não UTC): evita que o fuso do runner altere os valores esperados de HH:mm.
const NOW = new Date(2026, 10, 1, 20, 51, 0);

function isoMinutesAgo(minutes: number): string {
  return new Date(NOW.getTime() - minutes * 60 * 1000).toISOString();
}

function isoHoursAgo(hours: number): string {
  return isoMinutesAgo(hours * 60);
}

describe('formatLastChecked', () => {
  it('returns "agora mesmo" for less than a minute ago', () => {
    expect(formatLastChecked(isoMinutesAgo(0.5), NOW)).toBe('agora mesmo');
  });

  it('returns minutes for less than an hour ago', () => {
    expect(formatLastChecked(isoMinutesAgo(5), NOW)).toBe('há 5 min');
    expect(formatLastChecked(isoMinutesAgo(59), NOW)).toBe('há 59 min');
  });

  it('returns hours for less than a day ago', () => {
    expect(formatLastChecked(isoHoursAgo(3), NOW)).toBe('há 3 h');
    expect(formatLastChecked(isoHoursAgo(23), NOW)).toBe('há 23 h');
  });

  it('returns "ontem, HH:mm" for 1-2 days ago', () => {
    expect(formatLastChecked(isoHoursAgo(25), NOW)).toBe('ontem, 19:51');
  });

  it('returns "DD/MM, HH:mm" for more than 2 days ago', () => {
    const iso = new Date(2026, 9, 28, 20, 51, 0).toISOString();
    expect(formatLastChecked(iso, NOW)).toBe('28/10, 20:51');
  });
});

describe('isStale', () => {
  it('is false right after checking', () => {
    expect(isStale(isoHoursAgo(0), NOW)).toBe(false);
  });

  it('is false at exactly under 12h', () => {
    expect(isStale(isoHoursAgo(11), NOW)).toBe(false);
  });

  it('is true for more than 12h', () => {
    expect(isStale(isoHoursAgo(13), NOW)).toBe(true);
  });
});
