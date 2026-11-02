import { useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { Icon } from '@/components/Icon';
import { useNextCheck } from '../hooks/useNextCheck';
import { formatClock, formatDayLabel, formatRelative } from '../formatNextCheck';
import styles from './NextCheckCard.module.css';

/** Card do Dashboard: horário da próxima verificação automática de preços. */
export function NextCheckCard() {
  const { data, isLoading, isError, refetch } = useNextCheck();
  const [now, setNow] = useState(() => new Date());

  // Atualiza o "em X min" a cada 30s (só re-renderiza este card).
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  const next = data?.next_run ? new Date(data.next_run) : null;

  // Passou do horário → pede o próximo agendamento.
  const passed = next != null && next.getTime() <= now.getTime();
  useEffect(() => {
    if (passed) void refetch();
  }, [passed, refetch]);

  let value = '—';
  let label = 'Carregando agendamento…';
  if (!isLoading) {
    if (isError) {
      label = 'Agendamento indisponível';
    } else if (!next) {
      label = 'Sem verificação automática configurada';
    } else {
      value = formatClock(next);
      const every = data?.interval_hours ? ` · a cada ${data.interval_hours} horas` : '';
      label = `${formatDayLabel(next, now)} · ${formatRelative(next, now)}${every}`;
    }
  }

  return (
    <Card>
      <div className={styles.stat}>
        <span className={styles.eyebrow}>
          <Icon name="refresh" size={13} />
          Próxima verificação automática
        </span>
        <span className={styles.value}>
          {next && !isError ? <time dateTime={next.toISOString()}>{value}</time> : value}
        </span>
        <span className={styles.label}>{label}</span>
      </div>
    </Card>
  );
}
