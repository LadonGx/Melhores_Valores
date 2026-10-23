import { describe, expect, it } from 'vitest';
import type { RefreshAllStatus } from '@mv/types';
import {
  describeRefreshAllFinished,
  describeRefreshError,
  describeRefreshResult,
} from './refreshMessages';

const finished = (over: Partial<RefreshAllStatus>): RefreshAllStatus => ({
  running: false, total: 0, done: 0, ok: 0, failed: 0, ...over,
});

describe('describeRefreshResult', () => {
  it('formats the new price', () => {
    const fb = describeRefreshResult({ status: 'ok', price: 1234.5, in_stock: true, name: 'X', source: 'cascata' });
    expect(fb.type).toBe('success');
    expect(fb.message).toMatch(/^Preço atualizado: R\$\s?1\.234,50$/);
  });

  it('flags out of stock next to the price', () => {
    const fb = describeRefreshResult({ status: 'ok', price: 10, in_stock: false, name: null, source: 'cascata' });
    expect(fb.message).toContain('Sem estoque');
  });

  it('uses the backend message for out of stock and errors', () => {
    expect(describeRefreshResult({ status: 'out_of_stock', in_stock: false, detail: 'Fora de estoque.' }))
      .toEqual({ message: 'Fora de estoque.', type: 'success' });
    expect(describeRefreshResult({ status: 'error', reason: 'blocked', detail: 'Bloqueado.' }))
      .toEqual({ message: 'Bloqueado.', type: 'error' });
  });
});

describe('describeRefreshError', () => {
  it('explains timeouts', () => {
    expect(describeRefreshError(new Error('timeout of 60000ms exceeded')).message).toContain('Tempo esgotado');
  });

  it('falls back to the raw message', () => {
    expect(describeRefreshError(new Error('Network Error'))).toEqual({
      message: 'Erro ao atualizar preço: Network Error',
      type: 'error',
    });
  });
});

describe('describeRefreshAllFinished', () => {
  it('all good', () => {
    expect(describeRefreshAllFinished(finished({ total: 5, done: 5, ok: 5 }))).toEqual({
      message: 'Checagem concluída: 5 de 5 produtos atualizados.',
      type: 'success',
    });
  });

  it('partial failure is still a success with a note', () => {
    const fb = describeRefreshAllFinished(finished({ total: 5, done: 5, ok: 3, failed: 2 }));
    expect(fb.type).toBe('success');
    expect(fb.message).toContain('3 de 5 atualizados · 2 não puderam');
  });

  it('nothing worked is an error', () => {
    expect(describeRefreshAllFinished(finished({ total: 2, done: 2, failed: 2 })).type).toBe('error');
  });

  it('no active products', () => {
    expect(describeRefreshAllFinished(finished({})).message).toBe('Nenhum produto ativo para atualizar.');
  });
});
