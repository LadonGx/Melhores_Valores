import { useCallback, useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ProductGroup } from '@mv/types';
import { groupsService } from '@/services/groups';

/** Onde os grupos ficavam antes de irem para o banco (só lido para migrar). */
export const LEGACY_STORAGE_KEY = 'mv_product_groups';

export const groupKeys = {
  all: ['groups'] as const,
};

function readLegacyGroups(): ProductGroup[] {
  try {
    const raw = localStorage.getItem(LEGACY_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? (parsed as ProductGroup[]) : [];
  } catch {
    return [];
  }
}

/**
 * Grupos de anúncios do mesmo produto, guardados no banco (antes ficavam no
 * localStorage, fora do backup e sujeitos a sumir se os dados da janela fossem
 * limpos). Na primeira vez, envia ao backend os grupos que ainda estiverem no
 * localStorage e apaga a cópia local.
 */
export function useProductGroups() {
  const queryClient = useQueryClient();
  const { data: groups = [] } = useQuery({
    queryKey: groupKeys.all,
    queryFn: groupsService.list,
  });

  const invalidate = useCallback(
    () => queryClient.invalidateQueries({ queryKey: groupKeys.all }),
    [queryClient],
  );

  const migrationStarted = useRef(false);
  useEffect(() => {
    if (migrationStarted.current) return;
    migrationStarted.current = true;
    const legacy = readLegacyGroups();
    if (legacy.length === 0) return;
    groupsService
      .importLegacy(legacy)
      .then(() => {
        localStorage.removeItem(LEGACY_STORAGE_KEY);
        invalidate();
      })
      .catch(() => {
        // Mantém a cópia local para tentar de novo na próxima abertura
      });
  }, [invalidate]);

  const { mutate: createMutate } = useMutation({
    mutationFn: ({ name, productIds }: { name: string; productIds: string[] }) =>
      groupsService.create(name.trim(), productIds),
    onSuccess: invalidate,
  });

  const { mutate: removeMutate } = useMutation({
    mutationFn: (groupId: string) => groupsService.remove(groupId),
    // O backend já pode ter desfeito o grupo (ex: produtos excluídos): recarrega de qualquer jeito
    onSettled: invalidate,
  });

  const { mutate: ungroupMutate } = useMutation({
    mutationFn: ({ groupId, productId }: { groupId: string; productId: string }) => {
      const group = queryClient.getQueryData<ProductGroup[]>(groupKeys.all)?.find((g) => g.id === groupId);
      const remaining = (group?.productIds ?? []).filter((id) => id !== productId);
      // Com menos de 2 anúncios o backend desfaz o grupo (mesma regra de antes)
      return groupsService.update(groupId, { productIds: remaining });
    },
    onSettled: invalidate,
  });

  const createGroup = useCallback(
    (name: string, productIds: string[]) => createMutate({ name, productIds }),
    [createMutate],
  );
  const deleteGroup = useCallback((groupId: string) => removeMutate(groupId), [removeMutate]);
  const ungroupProduct = useCallback(
    (groupId: string, productId: string) => ungroupMutate({ groupId, productId }),
    [ungroupMutate],
  );

  return { groups, createGroup, deleteGroup, ungroupProduct };
}
