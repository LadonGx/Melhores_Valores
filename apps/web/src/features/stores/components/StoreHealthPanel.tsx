import { useState } from 'react';
import type { StoreChannelHealth, StoreHealth } from '@mv/types';
import { Icon } from '@/components/Icon';
import { useStoresHealth } from '../hooks/useStoresHealth';
import { StoreStatusDot } from './StoreStatusDot';
import styles from './StoreHealthPanel.module.css';

const CHANNEL_LABEL = { search: 'Busca', monitor: 'Monitoramento' } as const;

function formatWhen(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  const today = new Date();
  const time = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === today.toDateString()) return time;
  return `${d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })} ${time}`;
}

/** Frase curta da loja: "Funcionando", "Busca exigindo login", "Monitoramento falhando"… */
function summary(store: StoreHealth): string {
  if (store.status === 'ok') return 'Funcionando';
  if (store.status === 'unknown') return 'Sem dados recentes';
  const failing = (Object.keys(store.channels) as Array<keyof StoreHealth['channels']>).filter(
    (c) => store.channels[c].status === 'blocked' || store.channels[c].status === 'error',
  );
  if (failing.length === 1) {
    const c = failing[0];
    return `${CHANNEL_LABEL[c]} ${store.channels[c].detail}`;
  }
  return 'Busca e monitoramento com falhas';
}

function channelLine(channel: StoreChannelHealth): string {
  if (channel.status === 'ok') {
    const when = formatWhen(channel.last_ok_at);
    return when ? `funcionando · ${when}` : 'funcionando';
  }
  if (channel.status === 'unknown') return 'sem verificações recentes';
  const since = formatWhen(channel.last_fail_at);
  return since ? `${channel.detail} · desde ${since}` : channel.detail;
}

interface StoreHealthPanelProps {
  /** Sidebar recolhida: mostra só as bolinhas. */
  compact?: boolean;
}

/** Saúde das lojas na sidebar — explica bloqueios (ex.: ML exigindo login na busca). */
export function StoreHealthPanel({ compact = false }: StoreHealthPanelProps) {
  const { data, isError } = useStoresHealth();
  const [open, setOpen] = useState(false);
  const stores = data?.stores ?? [];

  if (isError || stores.length === 0) return null;

  if (compact) {
    return (
      <div className={styles.compact}>
        {stores.map((s) => (
          <span key={s.store} className={styles.compactItem} title={`${s.label}: ${summary(s)}`}>
            <StoreStatusDot status={s.status} />
            <span className={styles.srOnly}>{`${s.label}: ${summary(s)}`}</span>
          </span>
        ))}
      </div>
    );
  }

  return (
    <section className={styles.panel} aria-label="Status das lojas">
      <button
        type="button"
        className={styles.header}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className={styles.title}>Lojas</span>
        <Icon name="chevronDown" size={14} className={`${styles.chevron} ${open ? styles.chevronOpen : ''}`} />
      </button>

      <ul className={styles.list}>
        {stores.map((s) => (
          <li key={s.store} className={styles.store}>
            <div className={styles.storeRow}>
              <StoreStatusDot status={s.status} />
              <span className={styles.storeName}>{s.label}</span>
            </div>
            <span className={`${styles.summary} ${styles[s.status]}`}>{summary(s)}</span>

            {open && (
              <dl className={styles.channels}>
                {(Object.keys(s.channels) as Array<keyof StoreHealth['channels']>).map((c) => (
                  <div key={c} className={styles.channel}>
                    <dt>
                      <StoreStatusDot status={s.channels[c].status} size={6} />
                      {CHANNEL_LABEL[c]}
                    </dt>
                    <dd>{channelLine(s.channels[c])}</dd>
                  </div>
                ))}
              </dl>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
