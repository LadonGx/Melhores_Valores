import type { SellerType } from '@mv/types';

/** Preço vendido por terceiros (na caixa de compra ou só "a partir de"). */
export function isThirdParty(sellerType: SellerType | null | undefined): boolean {
  return sellerType === 'third_party' || sellerType === 'third_party_from';
}

/** Selo curto ao lado do preço; `null` quando o preço é da própria loja ou o vendedor é desconhecido. */
export function sellerBadge(sellerType: SellerType | null | undefined): string | null {
  if (sellerType === 'third_party') return 'Terceiro';
  if (sellerType === 'third_party_from') return 'Terceiros · a partir de';
  return null;
}

/** Texto curto da coluna "Vendedor" do histórico. */
export function sellerColumnLabel(
  sellerType: SellerType | null | undefined,
  sellerName?: string | null,
): string {
  if (sellerType === 'amazon') return 'Amazon';
  if (sellerType === 'third_party') return sellerName ?? 'Terceiro';
  if (sellerType === 'third_party_from') return 'Terceiros · a partir de';
  return '—';
}

/** Descrição completa do vendedor (tooltip, histórico); `null` quando não identificado. */
export function describeSeller(
  sellerType: SellerType | null | undefined,
  sellerName?: string | null,
): string | null {
  if (sellerType === 'amazon') return 'Vendido pela Amazon';
  if (sellerType === 'third_party') {
    return sellerName ? `Vendido por ${sellerName} (terceiro)` : 'Vendido por terceiro';
  }
  if (sellerType === 'third_party_from') return 'Só outros vendedores (menor preço "a partir de")';
  return null;
}
