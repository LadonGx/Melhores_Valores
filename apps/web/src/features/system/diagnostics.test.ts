import { afterEach, describe, it, expect, vi } from 'vitest';
import type { SystemInfo, UpdateInfo } from '@mv/types';
import {
  buildDiagnosticText,
  copyToClipboard,
  describeBrowser,
  describeFirecrawl,
  describeUpdate,
} from './diagnostics';

const info: SystemInfo = {
  version: '0.1.0',
  frozen: true,
  data_dir: 'C:\\Users\\Ana\\AppData\\Local\\MelhoresValores',
  db_path: 'C:\\Users\\Ana\\AppData\\Local\\MelhoresValores\\melhores_valores.db',
  log_file: 'C:\\Users\\Ana\\AppData\\Local\\MelhoresValores\\logs\\app.log',
  browser: null,
  firecrawl_configured: false,
  last_full_check: null,
  os: 'Windows-11-10.0.26200-SP0',
  python: '3.12.3',
};

const update: UpdateInfo = {
  current: '0.1.0', latest: '0.1.0', update_available: false, url: 'https://x', published_at: null, error: null,
};

describe('diagnostics', () => {
  it('describes browser and Firecrawl', () => {
    expect(describeBrowser(null)).toBe('Ainda não usado nesta abertura');
    expect(describeBrowser('Microsoft Edge')).toBe('Microsoft Edge');
    expect(describeFirecrawl(true)).toContain('Ligado');
    expect(describeFirecrawl(false)).toBe('Desligado');
  });

  it('describes the update state', () => {
    expect(describeUpdate(undefined)).toBe('Verificando…');
    expect(describeUpdate(update)).toBe('Você está na versão mais recente');
    expect(describeUpdate({ ...update, latest: '0.2.0', update_available: true })).toBe('Nova versão disponível: 0.2.0');
    expect(describeUpdate({ ...update, error: 'Não foi possível consultar o GitHub agora.' }))
      .toBe('Não foi possível consultar o GitHub agora.');
  });

  it('builds the text a tester pastes when reporting a problem', () => {
    const text = buildDiagnosticText(info, update);
    expect(text.split('\n')).toEqual([
      'Melhores Valores 0.1.0 (executável)',
      'Atualização: Você está na versão mais recente',
      'Navegador do scraping: Ainda não usado nesta abertura',
      'Firecrawl: Desligado',
      'Última checagem completa: nenhuma ainda',
      'Sistema: Windows-11-10.0.26200-SP0 · Python 3.12.3',
      `Pasta de dados: ${info.data_dir}`,
      `Log: ${info.log_file}`,
    ]);
  });
});

describe('copyToClipboard', () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubClipboard(writeText: () => Promise<void>) {
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: vi.fn(writeText) } });
  }

  it('uses the Clipboard API when allowed', async () => {
    stubClipboard(() => Promise.resolve());
    expect(await copyToClipboard('texto')).toBe(true);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('texto');
  });

  it('falls back to execCommand when the Clipboard API is denied', async () => {
    stubClipboard(() => Promise.reject(new Error('denied')));
    document.execCommand = vi.fn(() => true);
    expect(await copyToClipboard('texto')).toBe(true);
    expect(document.execCommand).toHaveBeenCalledWith('copy');
    expect(document.querySelector('textarea')).toBeNull(); // limpa o campo temporário
  });

  it('reports failure when nothing works', async () => {
    stubClipboard(() => Promise.reject(new Error('denied')));
    document.execCommand = vi.fn(() => false);
    expect(await copyToClipboard('texto')).toBe(false);
  });
});