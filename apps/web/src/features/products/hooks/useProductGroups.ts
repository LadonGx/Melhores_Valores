import { useCallback, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ProductGroup } from '@mv/types';
import { groupsService } from '@/services/groups';

export const groupKeys = {
  all: ['groups'] as const,
};

/** Chave antiga: os grupos ficavam só no localStorage deste navegador. */
const LEGACY_STORAGE_KEY = 'mv_product_groups';

function readLegacyGroups(): ProductGroup[] {
  try {
    const raw = localStorage.getItem(LEGACY_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ProductGroup[]) : [];
  } catch {
    return [];
  }
}

/**
 * O servidor recusou o grupo de vez (4xx: anúncios que não existem mais, anúncio já
 * em outro grupo...). Sem resposta ou 5xx é falha passageira: vale tentar de novo.
 */
function isPermanentRejection(error: unknown): boolean {
  const status = (error as { status?: number } | null)?.status;
  return typeof status === 'number' && status >= 400 && status < 500;
}

/**
 * Envia para o servidor os grupos que ainda estão no localStorage (versões antigas
 * salvavam só no navegador). Grupos com o mesmo nome e os mesmos anúncios de um que
 * já existe no servidor não são duplicados. Os que falharem por erro passageiro
 * continuam no localStorage para a próxima tentativa; a chave só é apagada quando
 * todos foram migrados ou descartados de propósito.
 */
export async function migrateLegacyGroups(serverGroups: ProductGroup[]): Promise<boolean> {
  const legacy = readLegacyGroups().filter((g) => g.name?.trim() && g.productIds?.length >= 2);
  if (legacy.length === 0) return false;

  const signature = (g: Pick<ProductGroup, 'name' | 'productIds'>) =>
    `${g.name.trim()}|${[...g.productIds].sort().join(',')}`;
  const existing = new Set(serverGroups.map(signature));

  const retry: ProductGroup[] = [];
  for (const group of legacy) {
    if (existing.has(signature(group))) continue;
    try {
      await groupsService.create(group.name.trim(), group.productIds);
    } catch (error) {
      if (!isPermanentRejection(error)) retry.push(group);
    }
  }
  try {
    if (retry.length > 0) localStorage.setItem(LEGACY_STORAGE_KEY, JSON.stringify(retry));
    else localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // localStorage indisponível: nada a salvar ou limpar
  }
  return true;
}

export function useProductGroups() {
  const queryClient = useQueryClient();
  const { data: groups = [], isSuccess } = useQuery({
    queryKey: groupKeys.all,
    queryFn: groupsService.getAll,
  });

  useEffect(() => {
    if (!isSuccess) return;
    void migrateLegacyGroups(groups).then((migrated) => {
      if (migrated) void queryClient.invalidateQueries({ queryKey: groupKeys.all });
    });
    // Só uma vez, quando a primeira lista do servidor chega
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuccess]);

  const setGroups = useCallback(
    (update: (current: ProductGroup[]) => ProductGroup[]) =>
      queryClient.setQueryData<ProductGroup[]>(groupKeys.all, (current = []) => update(current)),
    [queryClient],
  );
  const refetch = useCallback(
    () => queryClient.invalidateQueries({ queryKey: groupKeys.all }),
    [queryClient],
  );

  const createMutation = useMutation({
    mutationFn: ({ name, productIds }: { name: string; productIds: string[] }) =>
      groupsService.create(name, productIds),
    onSuccess: (group) => setGroups((current) => [...current, group]),
    onSettled: refetch,
  });

  const deleteMutation = useMutation({
    mutationFn: (groupId: string) => groupsService.remove(groupId),
    onMutate: (groupId) => setGroups((current) => current.filter((g) => g.id !== groupId)),
    onSettled: refetch,
  });

  const ungroupMutation = useMutation({
    mutationFn: ({ groupId, productId }: { groupId: string; productId: string }) =>
      groupsService.removeProduct(groupId, productId),
    onMutate: ({ groupId, productId }) =>
      setGroups((current) =>
        current
          .map((g) =>
            g.id === groupId ? { ...g, productIds: g.productIds.filter((id) => id !== productId) } : g,
          )
          // Grupo com menos de 2 anúncios é desfeito (o servidor faz o mesmo)
          .filter((g) => g.productIds.length >= 2),
      ),
    onSettled: refetch,
  });

  const createGroup = useCallback(
    (name: string, productIds: string[]) => createMutation.mutate({ name: name.trim(), productIds }),
    [createMutation],
  );
  const deleteGroup = useCallback((groupId: string) => deleteMutation.mutate(groupId), [deleteMutation]);
  const ungroupProduct = useCallback(
    (groupId: string, productId: string) => ungroupMutation.mutate({ groupId, productId }),
    [ungroupMutation],
  );

  return { groups, createGroup, deleteGroup, ungroupProduct };
}
