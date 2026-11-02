# Tarefa B — Produtos + modais de produto (agente Claude #2)

Leia primeiro: `D:\Estudos\Melhores_Valores\conceitos\GUIA_VISUAL.md` (regras inegociáveis + tokens).
Referência: `conceitos/Mix · Produtos@1x.png`.

## Seus arquivos (só estes)
- `apps/web/src/pages/Products/index.tsx` e `Products.module.css`
- `apps/web/src/features/products/components/AddProductForm.tsx` / `.module.css`
- `apps/web/src/features/products/components/ProductDetailModal.tsx` / `.module.css`
- `apps/web/src/features/products/components/PriceHistoryChart.tsx` / `.module.css`
- `apps/web/src/features/products/components/PromotionsModal.tsx` / `.module.css`
(Não mexa em hooks/services.)

## O que fazer
1. Página Produtos: trocar o Card-com-título por `PageHeader` (título "Produtos monitorados",
   subtítulo "N anúncios · Amazon e Mercado Livre", ações "Buscar por nome" secondary e
   "+ Adicionar URL" primary — mesmos handlers/modais). Abaixo, um Card sem título envolvendo a
   Table. NÃO criar o toggle Lista/Cards do mockup.
2. Colunas na ordem do mockup: [checkbox] [thumb + Produto (nome editável como hoje + domínio/caminho
   da URL em 12px muted)] [Loja (selo)] [Preço atual (+ "Sem estoque" se for o caso)] [Adicionado
   em] [Atualizar preço (secondary sm)]. Manter renomear inline, seleção, toolbar de excluir,
   ConfirmModal, loading do refresh, estado de erro com "Tentar novamente".
   Thumb: usar `image_url` se existir (lazy, 34×46), senão placeholder `--color-surface-3`.
3. ProductDetailModal: cabeçalho com imagem + nome + selo loja + preço atual em destaque; menor
   preço histórico em `--color-accent`; links/ações existentes intactos. StockWarningBanner é da
   tarefa C — só use como está.
4. PriceHistoryChart (recharts): linha `--color-primary-soft` (leia a var via
   `getComputedStyle(document.documentElement)` uma vez, ou use os hex do global.css como
   constantes num só lugar), grid `--color-border` tracejado, eixos `--color-text-faint` 11px,
   tooltip com fundo `--color-surface-2` e borda strong, ponto de menor preço em accent se já
   existir essa informação. Desligar animação inicial do recharts se ela estiver ligada
   (`isAnimationActive={false}`) — é ganho de desempenho.
5. AddProductForm e PromotionsModal: visual do guia (inputs, botões, lista de promoções com selo
   accent).

## Pronto quando
- `pnpm --filter @mv/web typecheck` e `pnpm --filter @mv/web test` passam.
- Conferiu em http://localhost:3000/products e abrindo o modal de detalhe pelo Dashboard
  ("Ver →"). Não clique em Excluir/Atualizar preço em dados reais.
- Escreveu `conceitos/tarefas/B-relatorio.md` (arquivos, mudanças, pedidos ao coordenador,
  "STATUS: PRONTO"). Não faça commit.
