import { describe, expect, it } from 'vitest';
import { describeSeller, isThirdParty, sellerBadge, sellerColumnLabel } from './seller';

describe('isThirdParty', () => {
  it('terceiro na caixa de compra e "a partir de" são terceiros', () => {
    expect(isThirdParty('third_party')).toBe(true);
    expect(isThirdParty('third_party_from')).toBe(true);
  });

  it('Amazon e vendedor desconhecido não são terceiros', () => {
    expect(isThirdParty('amazon')).toBe(false);
    expect(isThirdParty(null)).toBe(false);
    expect(isThirdParty(undefined)).toBe(false);
  });
});

describe('sellerBadge', () => {
  it('mostra selo só para terceiros', () => {
    expect(sellerBadge('third_party')).toBe('Terceiro');
    expect(sellerBadge('third_party_from')).toBe('Terceiros · a partir de');
    expect(sellerBadge('amazon')).toBeNull();
    expect(sellerBadge(null)).toBeNull();
  });
});

describe('sellerColumnLabel', () => {
  it('mostra o nome do terceiro quando existe', () => {
    expect(sellerColumnLabel('amazon')).toBe('Amazon');
    expect(sellerColumnLabel('third_party', 'JS Digital BR')).toBe('JS Digital BR');
    expect(sellerColumnLabel('third_party')).toBe('Terceiro');
    expect(sellerColumnLabel('third_party_from')).toBe('Terceiros · a partir de');
    expect(sellerColumnLabel(null)).toBe('—');
  });
});

describe('describeSeller', () => {
  it('descreve cada tipo de vendedor', () => {
    expect(describeSeller('amazon')).toBe('Vendido pela Amazon');
    expect(describeSeller('third_party', 'JS Digital BR')).toBe('Vendido por JS Digital BR (terceiro)');
    expect(describeSeller('third_party', null)).toBe('Vendido por terceiro');
    expect(describeSeller('third_party_from')).toBe('Só outros vendedores (menor preço "a partir de")');
  });

  it('vendedor não identificado não tem descrição', () => {
    expect(describeSeller(null)).toBeNull();
    expect(describeSeller(undefined, 'qualquer')).toBeNull();
  });
});
