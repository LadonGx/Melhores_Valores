# Tarefa A — Dashboard (agente Claude #1)

Leia primeiro: `D:\Estudos\Melhores_Valores\conceitos\GUIA_VISUAL.md` (regras inegociáveis + tokens).
Referência: `conceitos/Mix · Dashboard@1x.png`.

## Seus arquivos (só estes)
- `apps/web/src/pages/Dashboard/index.tsx`
- `apps/web/src/pages/Dashboard/Dashboard.module.css`
- `apps/web/src/pages/Dashboard/FilterMenu.tsx` e `FilterMenu.module.css`
(Não mexa em `sortRows.ts`, `useDashboardFilter.ts` nem nos testes.)

## O que fazer
1. `PageHeader` no topo: título = saudação por horário ("Bom dia!" 5–12h, "Boa tarde!" 12–18h,
   "Boa noite!" resto), subtítulo "N anúncios monitorados na Amazon e no Mercado Livre" (N do dado
   já carregado). Ação: botão primário "Buscar produto" que **só navega** para `/search`
   (`useNavigate` ou `Link`). NÃO criar a caixa "Buscar anúncio…" do mockup (seria função nova).
2. Stats: manter todos os cards existentes (anúncios, grupos, promoção/promoções — inclusive o
   clique que abre PromotionsModal). Visual do guia; valor da promoção pode usar `--color-accent`.
3. **Destaques** (novo, derivado): seção "Destaques" com até 4 cards dos produtos de menor
   `current_price` **da lista já carregada** (ignorar sem preço). Card: imagem (lazy, altura fixa
   ~96px, `object-fit: contain` sobre `--color-surface-3`), selo da loja, nome (2 linhas, ellipsis),
   preço grande. Clicar no card abre o **mesmo** ProductDetailModal que a linha abre hoje (reusar o
   handler existente). Se houver < 1 produto com preço, não renderizar a seção. Grid 4 colunas →
   2 abaixo de 900px.
4. Painel "Produtos monitorados": manter TUDO (checkbox, seleção, toolbar de grupo com nome,
   excluir, FilterMenu, GroupRow expansível, ProductRow, "Ver →"). Só o visual: linha do guia
   (thumb, nome + "Verificado em …", selo loja à direita, preço, "Ver →" lilás). Não reduzir a
   lista nem criar "Ver todos".
5. FilterMenu: popover com `--color-surface`, borda strong, `--shadow-lg`, ícone `filter` no gatilho.

## Pronto quando
- `pnpm --filter @mv/web typecheck` e `pnpm --filter @mv/web test` passam.
- Conferiu em http://localhost:3000/ (sidebar aberta e recolhida).
- Escreveu `conceitos/tarefas/A-relatorio.md` com: arquivos alterados, o que mudou, qualquer coisa
  que precisou do coordenador, e "STATUS: PRONTO". Não faça commit.
