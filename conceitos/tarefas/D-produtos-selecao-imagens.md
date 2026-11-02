# Tarefa D — Produtos: seleção com barra flutuante + qualidade das imagens (agente Claude)

Leia primeiro `D:\Estudos\Melhores_Valores\conceitos\GUIA_VISUAL.md`, **principalmente a seção
"Fase 2"**, e a referência `conceitos/Seleção · Barra flutuante@1x.png`.
Mesmas regras inegociáveis da fase 1 (só aparência, handlers intactos, testes passando, sem commit).

## Seus arquivos (só estes)
- `apps/web/src/pages/Products/index.tsx` e `Products.module.css`
- `apps/web/src/features/products/components/ProductDetailModal.module.css` (só as miniaturas)
- `apps/web/src/features/products/components/PromotionsModal.tsx` / `.module.css` (só as miniaturas, se houver)
O coordenador está editando o Dashboard e componentes base ao mesmo tempo: não toque neles.
Já prontos para você usar: `@/components/SelectionBar`, `Button variant="dangerOutline"`,
`Column.header` da Table agora aceita ReactNode, prop `rowClassName` na Table, tokens `--color-selection-bg/-border`.

## O que fazer
1. **Seleção na tabela de Produtos** no padrão do exemplo:
   - Linha selecionada arredondada/suave (fundo e borda de seleção). Na `<table>` use as células:
     a 1ª e a última `td` da linha recebem os cantos arredondados e a borda é feita com
     `box-shadow: inset` ou borda nas `td` (teste no navegador até ficar igual ao exemplo). Para
     marcar a linha use a prop nova da Table: `rowClassName={(r) => selectedIds.has(r.id) ? styles.rowSelected : undefined}`
     (não edite a Table).
   - Checkbox "Selecionar todos" no cabeçalho da coluna de seleção (header ReactNode), ligado ao
     `toggleSelectAll` existente, com `aria-label="Selecionar todos"`.
   - A toolbar atual (Selecionar todos / Excluir / Cancelar) sai de dentro do Card e vira
     `<SelectionBar count={selectedIds.size} onClear={() => setSelectedIds(new Set())}>` com o botão
     `Excluir` (`dangerOutline`, ícone `trash`) abrindo o mesmo ConfirmModal de hoje. Coloque a
     SelectionBar como último filho da página.
2. **Imagens**: miniatura da tabela 44×56 `object-fit: contain` (hoje está 34×46 `cover`, cortando
   produtos quadrados). Mesmo critério nas miniaturas do ProductDetailModal (cabeçalho 56×56 já ok —
   só garanta `contain`) e do PromotionsModal.

## Pronto quando
- `pnpm --filter @mv/web typecheck` e `pnpm --filter @mv/web test` passam.
- Conferiu em http://localhost:3000/products marcando/desmarcando linhas (NÃO clique em "Excluir"
  confirmando — pode abrir o ConfirmModal e cancelar).
- Escreveu `conceitos/tarefas/D-relatorio.md` (arquivos, mudanças, pedidos, "STATUS: PRONTO").
