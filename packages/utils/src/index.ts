const BRL_FORMATTER = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
});

const DATE_FORMATTER = new Intl.DateTimeFormat('pt-BR', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

export function formatCurrency(value: number): string {
  return BRL_FORMATTER.format(value);
}

export function formatDate(iso: string): string {
  return DATE_FORMATTER.format(new Date(iso));
}

export function formatStore(store: string): string {
  const map: Record<string, string> = {
    amazon: 'Amazon',
    mercadolivre: 'Mercado Livre',
    shopee: 'Shopee',
    magalu: 'Magazine Luiza',
  };
  return map[store.toLowerCase()] ?? store;
}

export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}
