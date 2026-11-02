const MINUTE = 60_000;
const DAY = 24 * 60 * MINUTE;

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** "21:00" no fuso do navegador. */
export function formatClock(date: Date): string {
  return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

/** "Hoje", "Amanhã" ou "05/11". */
export function formatDayLabel(date: Date, now: Date): string {
  const diffDays = Math.round((startOfDay(date) - startOfDay(now)) / DAY);
  if (diffDays === 0) return 'Hoje';
  if (diffDays === 1) return 'Amanhã';
  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

/** "em 1h 12min", "em 15 min", "em instantes". */
export function formatRelative(date: Date, now: Date): string {
  const minutes = Math.ceil((date.getTime() - now.getTime()) / MINUTE);
  if (minutes <= 1) return 'em instantes';
  if (minutes < 60) return `em ${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `em ${h}h` : `em ${h}h ${m}min`;
}
