import type { Product } from '@mv/types';

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** 12h = 2 ciclos perdidos do agendamento automático (roda a cada 6h). */
const STALE_THRESHOLD = 12 * HOUR;

function pad(n: number): string {
  return n.toString().padStart(2, '0');
}

function formatTime(date: Date): string {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatShortDate(date: Date): string {
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}`;
}

/**
 * Texto relativo para a última verificação de preço: "há 5 min", "há 3 h",
 * "ontem, 18:41", "28/10, 20:51". `now` é injetável para testes.
 */
export function formatLastChecked(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const diffMs = now.getTime() - date.getTime();

  if (diffMs < MINUTE) return 'agora mesmo';
  if (diffMs < HOUR) return `há ${Math.floor(diffMs / MINUTE)} min`;
  if (diffMs < DAY) return `há ${Math.floor(diffMs / HOUR)} h`;
  if (diffMs < 2 * DAY) return `ontem, ${formatTime(date)}`;
  return `${formatShortDate(date)}, ${formatTime(date)}`;
}

/** Mais de 12h sem verificação (2 ciclos de 6h do agendamento automático perdidos). */
export function isStale(iso: string, now: Date = new Date()): boolean {
  return now.getTime() - new Date(iso).getTime() > STALE_THRESHOLD;
}

// ─── Estado da última verificação (GET /products) ────────────────────────────

/** Campos de verificação que o backend expõe em cada produto. */
export type LastCheckFields = Pick<
  Product,
  'last_checked' | 'last_attempt_at' | 'last_check_status' | 'last_check_error'
>;

/** Rótulo curto do motivo da falha, em português. Desconhecido → "erro". */
export function formatCheckErrorLabel(error: string | null | undefined): string {
  const labels: Record<string, string> = {
    login_wall: 'exigindo login',
    captcha: 'pedindo captcha',
    access_denied: 'acesso negado',
    rate_limited: 'limite de acessos',
    challenge_js: 'desafio anti-robô',
    scrape_failed: 'página não carregou',
    invalid_price: 'preço não encontrado',
    price_rejected: 'preço suspeito descartado',
    exception: 'erro interno',
  };
  return (error != null && labels[error]) || 'erro';
}

/**
 * A última tentativa FALHOU quando o status é `error`/`blocked` e não houve
 * sucesso depois dela: `last_checked` nulo ou `last_attempt_at` posterior.
 * (Sucesso posterior ao erro reseta o estado para o último "Verificado".)
 */
export function lastCheckFailed(product: LastCheckFields): boolean {
  const { last_check_status, last_checked, last_attempt_at } = product;
  if (last_check_status !== 'error' && last_check_status !== 'blocked') return false;
  if (!last_checked) return true;
  return !!last_attempt_at && new Date(last_attempt_at).getTime() > new Date(last_checked).getTime();
}

/** Data da última tentativa (sucesso ou falha): `last_attempt_at` com fallback para `last_checked`. */
export function lastAttemptAt(product: LastCheckFields): string | null {
  return product.last_attempt_at ?? product.last_checked ?? null;
}

export type LastCheckDisplay =
  /** Nunca houve checagem. */
  | { kind: 'none' }
  /** Última tentativa falhou/bloqueou. */
  | {
      kind: 'failed';
      /** Texto completo: "Falhou há 2 h · exigindo login". */
      text: string;
      label: string;
      /** Última verificação bem-sucedida, se houver (para title/aria). */
      checkedAt: string | null;
    }
  /** Última checagem teve sucesso; `noOffer` marca "sem oferta principal". */
  | { kind: 'success'; noOffer: boolean; when: string; checkedAt: string; stale: boolean };

/**
 * Estado de exibição da última verificação de um produto, a partir dos campos
 * do GET /products. `now` é injetável para testes.
 */
export function describeLastCheck(product: LastCheckFields, now: Date = new Date()): LastCheckDisplay {
  if (lastCheckFailed(product)) {
    const label = formatCheckErrorLabel(product.last_check_error);
    const when = product.last_attempt_at ? formatLastChecked(product.last_attempt_at, now) : null;
    return {
      kind: 'failed',
      text: when ? `Falhou ${when} · ${label}` : `Falhou · ${label}`,
      label,
      checkedAt: product.last_checked ?? null,
    };
  }
  if (!product.last_checked) return { kind: 'none' };
  return {
    kind: 'success',
    noOffer: product.last_check_status === 'no_offer',
    when: formatLastChecked(product.last_checked, now),
    checkedAt: product.last_checked,
    stale: isStale(product.last_checked, now),
  };
}
