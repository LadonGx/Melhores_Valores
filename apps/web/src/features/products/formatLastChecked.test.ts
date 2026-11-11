import { describe, it, expect } from 'vitest';
import {
  describeLastCheck,
  formatCheckErrorLabel,
  formatLastChecked,
  isStale,
  lastAttemptAt,
  lastCheckFailed,
  type LastCheckFields,
} from './formatLastChecked';

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

describe('formatCheckErrorLabel', () => {
  it('maps known reasons to short pt-BR labels', () => {
    expect(formatCheckErrorLabel('login_wall')).toBe('exigindo login');
    expect(formatCheckErrorLabel('captcha')).toBe('pedindo captcha');
    expect(formatCheckErrorLabel('access_denied')).toBe('acesso negado');
    expect(formatCheckErrorLabel('rate_limited')).toBe('limite de acessos');
    expect(formatCheckErrorLabel('challenge_js')).toBe('desafio anti-robô');
    expect(formatCheckErrorLabel('scrape_failed')).toBe('página não carregou');
    expect(formatCheckErrorLabel('invalid_price')).toBe('preço não encontrado');
    expect(formatCheckErrorLabel('price_rejected')).toBe('preço suspeito descartado');
    expect(formatCheckErrorLabel('exception')).toBe('erro interno');
  });

  it('falls back to "erro" for unknown or missing reasons', () => {
    expect(formatCheckErrorLabel('desconhecido')).toBe('erro');
    expect(formatCheckErrorLabel(null)).toBe('erro');
    expect(formatCheckErrorLabel(undefined)).toBe('erro');
  });
});

describe('lastCheckFailed', () => {
  it('is false without a failure status', () => {
    expect(lastCheckFailed({})).toBe(false);
    expect(lastCheckFailed({ last_check_status: null })).toBe(false);
  });

  it('is false for success statuses', () => {
    expect(lastCheckFailed({ last_check_status: 'ok', last_checked: isoHoursAgo(1) })).toBe(false);
    expect(lastCheckFailed({ last_check_status: 'out_of_stock', last_checked: isoHoursAgo(1) })).toBe(false);
    expect(lastCheckFailed({ last_check_status: 'no_offer', last_checked: isoHoursAgo(1) })).toBe(false);
  });

  it('is true when failed and never checked successfully', () => {
    expect(
      lastCheckFailed({ last_check_status: 'error', last_checked: null, last_attempt_at: isoHoursAgo(1) }),
    ).toBe(true);
    expect(lastCheckFailed({ last_check_status: 'blocked' })).toBe(true);
  });

  it('is true when the failed attempt is after the last success', () => {
    expect(
      lastCheckFailed({
        last_check_status: 'error',
        last_checked: isoHoursAgo(3),
        last_attempt_at: isoHoursAgo(1),
      }),
    ).toBe(true);
    expect(
      lastCheckFailed({
        last_check_status: 'blocked',
        last_checked: isoHoursAgo(3),
        last_attempt_at: isoHoursAgo(1),
      }),
    ).toBe(true);
  });

  it('is false when a success happened after the failure (old failure reset)', () => {
    expect(
      lastCheckFailed({
        last_check_status: 'error',
        last_checked: isoHoursAgo(1),
        last_attempt_at: isoHoursAgo(3),
      }),
    ).toBe(false);
    // Mesmo instante: a tentativa não é estritamente posterior ao sucesso.
    expect(
      lastCheckFailed({
        last_check_status: 'error',
        last_checked: isoHoursAgo(1),
        last_attempt_at: isoHoursAgo(1),
      }),
    ).toBe(false);
  });
});

describe('lastAttemptAt', () => {
  it('prefers last_attempt_at and falls back to last_checked', () => {
    expect(lastAttemptAt({ last_attempt_at: isoHoursAgo(1), last_checked: isoHoursAgo(3) })).toBe(isoHoursAgo(1));
    expect(lastAttemptAt({ last_checked: isoHoursAgo(3) })).toBe(isoHoursAgo(3));
    expect(lastAttemptAt({})).toBeNull();
  });
});

describe('describeLastCheck', () => {
  it('reports "none" when never checked', () => {
    expect(describeLastCheck({}, NOW)).toEqual({ kind: 'none' });
    expect(describeLastCheck({ last_check_status: null, last_checked: null }, NOW)).toEqual({ kind: 'none' });
  });

  it('reports success from last_checked', () => {
    expect(
      describeLastCheck({ last_check_status: 'ok', last_checked: isoHoursAgo(3) }, NOW),
    ).toEqual({
      kind: 'success',
      noOffer: false,
      when: 'há 3 h',
      checkedAt: isoHoursAgo(3),
      stale: false,
    });
  });

  it('flags stale success after 12h without turning it into a failure', () => {
    expect(
      describeLastCheck({ last_check_status: 'ok', last_checked: isoHoursAgo(13) }, NOW),
    ).toEqual({
      kind: 'success',
      noOffer: false,
      when: 'há 13 h',
      checkedAt: isoHoursAgo(13),
      stale: true,
    });
  });

  it('marks no_offer as success with the "sem oferta principal" indication', () => {
    expect(
      describeLastCheck({ last_check_status: 'no_offer', last_checked: isoHoursAgo(2) }, NOW),
    ).toEqual({
      kind: 'success',
      noOffer: true,
      when: 'há 2 h',
      checkedAt: isoHoursAgo(2),
      stale: false,
    });
  });

  it('describes a failed attempt with relative time and label', () => {
    const fields: LastCheckFields = {
      last_check_status: 'error',
      last_check_error: 'login_wall',
      last_checked: null,
      last_attempt_at: isoHoursAgo(2),
    };
    expect(describeLastCheck(fields, NOW)).toEqual({
      kind: 'failed',
      text: 'Falhou há 2 h · exigindo login',
      label: 'exigindo login',
      checkedAt: null,
    });
  });

  it('describes a blocked attempt', () => {
    const fields: LastCheckFields = {
      last_check_status: 'blocked',
      last_check_error: 'captcha',
      last_checked: null,
      last_attempt_at: isoMinutesAgo(30),
    };
    expect(describeLastCheck(fields, NOW)).toEqual({
      kind: 'failed',
      text: 'Falhou há 30 min · pedindo captcha',
      label: 'pedindo captcha',
      checkedAt: null,
    });
  });

  it('falls back to "Falhou · erro" without a timestamp or known reason', () => {
    expect(describeLastCheck({ last_check_status: 'error' }, NOW)).toEqual({
      kind: 'failed',
      text: 'Falhou · erro',
      label: 'erro',
      checkedAt: null,
    });
  });

  it('keeps the last successful check time accessible when a later attempt failed', () => {
    const fields: LastCheckFields = {
      last_check_status: 'blocked',
      last_check_error: 'rate_limited',
      last_checked: isoHoursAgo(5),
      last_attempt_at: isoHoursAgo(1),
    };
    expect(describeLastCheck(fields, NOW)).toEqual({
      kind: 'failed',
      text: 'Falhou há 1 h · limite de acessos',
      label: 'limite de acessos',
      checkedAt: isoHoursAgo(5),
    });
  });

  it('shows success when an old failure was followed by a successful check', () => {
    // Sucesso mais recente: backend grava last_checked = last_attempt_at e limpa o erro.
    const fields: LastCheckFields = {
      last_check_status: 'ok',
      last_check_error: null,
      last_checked: isoHoursAgo(1),
      last_attempt_at: isoHoursAgo(1),
    };
    expect(describeLastCheck(fields, NOW)).toEqual({
      kind: 'success',
      noOffer: false,
      when: 'há 1 h',
      checkedAt: isoHoursAgo(1),
      stale: false,
    });
  });

  it('shows stale success (not failure) when an old failure was followed by an old success', () => {
    const fields: LastCheckFields = {
      last_check_status: 'ok',
      last_check_error: null,
      last_checked: isoHoursAgo(13),
      last_attempt_at: isoHoursAgo(13),
    };
    expect(describeLastCheck(fields, NOW)).toEqual({
      kind: 'success',
      noOffer: false,
      when: 'há 13 h',
      checkedAt: isoHoursAgo(13),
      stale: true,
    });
  });
});
