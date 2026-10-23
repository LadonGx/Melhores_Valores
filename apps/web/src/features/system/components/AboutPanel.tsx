import { useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import {
  useForceUpdateCheck,
  useOpenFolder,
  useSystemInfo,
  useUpdateCheck,
} from '@/features/system/hooks/useSystem';
import {
  buildDiagnosticText,
  copyToClipboard,
  describeBrowser,
  describeFirecrawl,
  describeUpdate,
} from '@/features/system/diagnostics';
import { formatDate } from '@mv/utils';
import styles from './AboutPanel.module.css';

/**
 * Tela "Sobre": versão (e se há uma nova) e o diagnóstico que o testador manda
 * quando algo dá errado — com atalhos para a pasta de dados e o app.log.
 */
export function AboutPanel() {
  const { data: info, isLoading, isError, refetch } = useSystemInfo();
  const { data: update } = useUpdateCheck();
  const forceCheck = useForceUpdateCheck();
  const openFolder = useOpenFolder();
  const [copied, setCopied] = useState<'ok' | 'error' | null>(null);

  const copyDiagnostics = async () => {
    if (!info) return;
    setCopied((await copyToClipboard(buildDiagnosticText(info, update))) ? 'ok' : 'error');
  };

  return (
    <div className={styles.page}>
      <Card title="Melhores Valores">
        <div className={styles.versionRow}>
          <div>
            <div className={styles.version}>Versão {info?.version ?? update?.current ?? '…'}</div>
            <div className={update?.update_available ? styles.updateAvailable : styles.muted}>
              {describeUpdate(update)}
            </div>
          </div>
          <div className={styles.actions}>
            {update?.update_available && (
              <a href={update.url} target="_blank" rel="noreferrer" className={styles.download}>
                Baixar versão nova →
              </a>
            )}
            <Button variant="ghost" size="sm" loading={forceCheck.isPending} onClick={() => forceCheck.mutate()}>
              Verificar agora
            </Button>
          </div>
        </div>
      </Card>

      <Card
        title="Diagnóstico"
        action={
          <Button variant="secondary" size="sm" disabled={!info} onClick={copyDiagnostics}>
            {copied === 'ok' ? 'Copiado ✓' : 'Copiar diagnóstico'}
          </Button>
        }
      >
        {isError ? (
          <div className={styles.muted}>
            Não foi possível ler as informações do app.{' '}
            <Button variant="ghost" size="sm" onClick={() => refetch()}>Tentar novamente</Button>
          </div>
        ) : isLoading || !info ? (
          <div className={styles.muted}>Carregando…</div>
        ) : (
          <>
            <dl className={styles.list}>
              <dt>Navegador do scraping</dt>
              <dd>{describeBrowser(info.browser)}</dd>
              <dt>Firecrawl</dt>
              <dd>{describeFirecrawl(info.firecrawl_configured)}</dd>
              <dt>Última checagem completa</dt>
              <dd>{info.last_full_check ? formatDate(info.last_full_check) : 'Nenhuma ainda'}</dd>
              <dt>Sistema</dt>
              <dd>{info.os}</dd>
              <dt>Pasta de dados</dt>
              <dd className={styles.path}>{info.data_dir}</dd>
              <dt>Arquivo de log</dt>
              <dd className={styles.path}>{info.log_file}</dd>
            </dl>

            <div className={styles.folderActions}>
              <Button variant="secondary" size="sm" onClick={() => openFolder.mutate('data')}>
                Abrir pasta de dados
              </Button>
              <Button variant="secondary" size="sm" onClick={() => openFolder.mutate('logs')}>
                Abrir pasta de logs
              </Button>
            </div>

            {copied === 'error' && (
              <>
                <p className={styles.error}>Não foi possível copiar automaticamente. Copie o texto abaixo (Ctrl+C):</p>
                <textarea
                  className={styles.fallback}
                  readOnly
                  rows={8}
                  value={buildDiagnosticText(info, update)}
                  onFocus={(e) => e.currentTarget.select()}
                  autoFocus
                />
              </>
            )}
            {openFolder.isError && <p className={styles.error}>Não foi possível abrir a pasta.</p>}
            <p className={styles.help}>
              Algo deu errado? Clique em <strong>Copiar diagnóstico</strong> e envie junto com o arquivo{' '}
              <code>app.log</code> (em <strong>Abrir pasta de logs</strong>) para quem te passou o app.
            </p>
          </>
        )}
      </Card>
    </div>
  );
}
