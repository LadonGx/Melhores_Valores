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
