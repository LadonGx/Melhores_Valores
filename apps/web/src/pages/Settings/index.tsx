import { Card } from '@/components/Card';
import styles from './Settings.module.css';

export function Settings() {
  const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  return (
    <div className={styles.page}>
      <Card title="Configurações da API">
        <dl className={styles.config}>
          <div className={styles.configItem}>
            <dt>URL da API</dt>
            <dd><code>{apiUrl}</code></dd>
          </div>
          <div className={styles.configItem}>
            <dt>Variável de ambiente</dt>
            <dd><code>VITE_API_URL</code></dd>
          </div>
        </dl>
        <p className={styles.hint}>
          Para alterar a URL da API, defina a variável <code>VITE_API_URL</code> no arquivo <code>apps/web/.env</code>.
        </p>
      </Card>
    </div>
  );
}
