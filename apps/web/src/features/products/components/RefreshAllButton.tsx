import { useState } from 'react';
import { Button } from '@/components/Button';
import { Toast } from '@/components/Toast';
import { useRefreshAll } from '@/features/products/hooks/useProducts';
import {
  describeRefreshAllFinished,
  describeRefreshError,
  type RefreshFeedback,
} from '@/features/products/refreshMessages';

/**
 * "Atualizar todos": checa de novo todos os produtos ativos. Mostra o progresso
 * no próprio botão — inclusive quando é a checagem automática de 6 h que está
 * rodando — e um aviso com o resumo ao terminar.
 */
export function RefreshAllButton() {
  const [toast, setToast] = useState<RefreshFeedback | null>(null);
  const { status, isRunning, start, isStarting } = useRefreshAll({
    onFinished: (finished) => setToast(describeRefreshAllFinished(finished)),
  });

  const label = isRunning && status
    ? `Atualizando ${status.done}/${status.total}…`
    : 'Atualizar todos';
  const title = isRunning && status?.trigger === 'agendada'
    ? 'Checagem automática em andamento'
    : 'Buscar agora o preço de todos os produtos ativos';

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        loading={isStarting}
        disabled={isRunning}
        title={title}
        onClick={() => start(undefined, { onError: (err) => setToast(describeRefreshError(err)) })}
      >
        {label}
      </Button>
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </>
  );
}
