import type { Product, ProductFormat } from '@mv/types';

/** O anúncio é a edição eBook Kindle (físico e desconhecido não são). */
export function isKindle(product: Product): boolean {
  return product.format === 'ebook_kindle';
}

/** Selo curto do formato: "Kindle" só para eBook Kindle; físico e desconhecido não têm selo. */
export function kindleBadge(product: Product): string | null {
  return isKindle(product) ? 'Kindle' : null;
}

/** Aviso de grupo com formatos não comparáveis (não bloqueia a ação). */
export const MIXED_FORMATS_WARNING =
  'Este grupo mistura eBook Kindle e edição física — os preços não são comparáveis.';

/**
 * true quando a lista tem pelo menos um eBook Kindle e uma edição física.
 * Formato desconhecido (null/ausente) não conta como nenhum dos dois.
 */
export function hasMixedFormats(products: Product[]): boolean {
  const formats = new Set<ProductFormat>();
  for (const product of products) {
    if (product.format === 'ebook_kindle' || product.format === 'physical') {
      formats.add(product.format);
      if (formats.size === 2) return true;
    }
  }
  return false;
}

/** Texto do aviso quando os anúncios misturam formatos; `null` quando não misturam. */
export function mixedFormatsWarning(products: Product[]): string | null {
  return hasMixedFormats(products) ? MIXED_FORMATS_WARNING : null;
}
