import type { RefreshAllStatus, RefreshPriceResponse } from '@mv/types';
import { formatCurrency } from '@mv/utils';

export interface RefreshFeedback {
  message: string;
  type: 'success' | 'error';
}

/** Mensagem do "Atualizar preço" de um produto (lista e modal de detalhes). */
export function describeRefreshResult(result: RefreshPriceResponse): RefreshFeedback {
  if (result.status === 'ok') {
    const priceStr = result.price != null ? formatCurrency(result.price) : '—';
    const stockStr = result.in_stock === false ? ' · Sem estoque' : '';
    return { message: `Preço atualizado: ${priceStr}${stockStr}`, type: 'success' };
  }
  // out_of_stock e erros já vêm com o texto amigável do backend
  return { message: result.detail, type: result.status === 'out_of_stock' ? 'success' : 'error' };
}

export function describeRefreshError(err: unknown): RefreshFeedback {
  const msg = err instanceof Error ? err.message : String(err);
  if (msg.toLowerCase().includes('timeout')) {
    return {
      message: 'Tempo esgotado ao buscar preço. O site pode estar lento. Tente novamente.',
      type: 'error',
    };
  }
  return { message: `Erro ao atualizar preço: ${msg}`, type: 'error' };
}

/** Resumo do fim da checagem completa ("Atualizar todos" ou a automática). */
export function describeRefreshAllFinished(status: RefreshAllStatus): RefreshFeedback {
  if (status.total === 0) {
    return { message: 'Nenhum produto ativo para atualizar.', type: 'success' };
  }
  if (status.failed === 0) {
    return { message: `Checagem concluída: ${status.ok} de ${status.total} produtos atualizados.`, type: 'success' };
  }
  return {
    message: `Checagem concluída: ${status.ok} de ${status.total} atualizados · ${status.failed} não puderam ser verificados agora.`,
    type: status.ok === 0 ? 'error' : 'success',
  };
}
