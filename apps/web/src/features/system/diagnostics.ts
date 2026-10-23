import type { SystemInfo, UpdateInfo } from '@mv/types';
import { formatDate } from '@mv/utils';

export function describeBrowser(browser: string | null): string {
  return browser ?? 'Ainda não usado nesta abertura';
}

export function describeFirecrawl(configured: boolean): string {
  return configured ? 'Ligado (chave própria no config.env)' : 'Desligado';
}

export function describeUpdate(update: UpdateInfo | undefined): string {
  if (!update) return 'Verificando…';
  if (update.error) return update.error;
  if (update.update_available && update.latest) return `Nova versão disponível: ${update.latest}`;
  return 'Você está na versão mais recente';
}

/**
 * Copia texto. Tenta a API moderna e cai para o execCommand('copy'), que a
 * janela do app (WebView2) aceita mesmo quando a API moderna é negada.
 * Retorna false se nenhum dos dois funcionar.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    try {
      return document.execCommand('copy');
    } catch {
      return false;
    } finally {
      document.body.removeChild(area);
    }
  }
}

/** Texto para o testador colar numa mensagem ao relatar um problema. */
export function buildDiagnosticText(info: SystemInfo, update?: UpdateInfo): string {
  return [
    `Melhores Valores ${info.version}${info.frozen ? ' (executável)' : ' (código-fonte)'}`,
    `Atualização: ${describeUpdate(update)}`,
    `Navegador do scraping: ${describeBrowser(info.browser)}`,
    `Firecrawl: ${describeFirecrawl(info.firecrawl_configured)}`,
    `Última checagem completa: ${info.last_full_check ? formatDate(info.last_full_check) : 'nenhuma ainda'}`,
    `Sistema: ${info.os} · Python ${info.python}`,
    `Pasta de dados: ${info.data_dir}`,
    `Log: ${info.log_file}`,
  ].join('\n');
}
