# Tarefa C — Buscar produto (agente OpenCode)

Leia primeiro: `D:\Estudos\Melhores_Valores\conceitos\GUIA_VISUAL.md` (regras inegociáveis + tokens).
Referência: `conceitos/Mix · Buscar produto@1x.png`.

## Seus arquivos (só estes)
- `apps/web/src/pages/Search/index.tsx` e `Search.module.css`
- `apps/web/src/features/search/components/SearchByName.tsx` e `SearchByName.module.css`
- `apps/web/src/features/products/components/StockWarningBanner.tsx` e `.module.css`
(Não mexa em `useSearch.ts` nem nos arquivos `*.test.tsx`.)

## O que fazer
1. Página Search: trocar o Card por `PageHeader` (título "Buscar produto", subtítulo com o texto
   atual de explicação, incluindo **Monitorar** em `<strong>`), e renderizar `<SearchByName />`
   logo abaixo, sem Card em volta.
2. SearchByName (também é usado dentro de um Modal na página Produtos — tem que ficar bom nos dois
   lugares): linha de formulário = input grande (flex 1, altura 48) + "Preço mín." + "Preço máx."
   (largura ~130) + botão primário "Buscar" (altura 48). Abaixo de 720px quebra em colunas.
   Aviso de loja bloqueada (ML exigindo login) com cores warning do guia, ícone `alert`.
   Resultados num painel (fundo surface, borda, radius lg): cabeçalho "N resultados";
   linhas = [selo loja] [thumb lazy] [nome] … [preço 16px/700 + selo "Menor preço" accent no 1º com
   preço] ou "Sem preço" faint, [botão secondary "Monitorar"]. Estado "Buscando em Amazon e
   Mercado Livre…" com spinner leve (CSS).
3. **Atenção aos testes** (`SearchByName.test.tsx`): placeholders, textos de validação, o nome do
   botão "Buscar" e o fato de existir **um único `button`** durante o loading NÃO podem mudar.
   Não adicione outros `<button>` visíveis no estado de loading.
4. StockWarningBanner: visual warning do guia, ícone `alert`.

## Pronto quando
- `pnpm --filter @mv/web typecheck` e `pnpm --filter @mv/web test` passam.
- Conferiu em http://localhost:3000/search (pode fazer uma busca — buscas não salvam produtos;
  NÃO clique em "Monitorar") e no modal "Buscar por nome" em /products.
- Escreveu `conceitos/tarefas/C-relatorio.md` (arquivos, mudanças, pedidos ao coordenador,
  "STATUS: PRONTO"). Não faça commit.
