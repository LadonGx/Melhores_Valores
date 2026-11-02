# Tarefa E — Buscar produto: esqueletos de carregamento + qualidade das imagens (agente OpenCode)

Leia primeiro `D:\Estudos\Melhores_Valores\conceitos\GUIA_VISUAL.md`, **principalmente a seção
"Fase 2"**. Mesmas regras da fase 1 (só aparência, testes passando, sem commit).

## Seus arquivos (só estes)
- `apps/web/src/features/search/components/SearchByName.tsx` e `SearchByName.module.css`
(Não mexa em `useSearch.ts` nem em `*.test.tsx`.)

## O que fazer
1. **Esqueleto de resultados**: enquanto a busca está em andamento, além da linha atual
   "Buscando em Amazon e Mercado Livre… Pode levar até 30s." (mantenha esse texto — os testes usam),
   mostre o painel de resultados com **6 linhas-esqueleto** no mesmo formato de uma linha real:
   [pílula de loja] [miniatura 44×56] [2 barras de texto: 60% e 35% da largura] … [barra de preço]
   [bloco do botão]. Cabeçalho do painel com uma barra curta no lugar de "N resultados".
   Os esqueletos são `<div>`/`<span>` com `aria-hidden="true"` — **NÃO** use `<button>` (o teste
   verifica que existe um único button durante o loading). Animação só de opacity (ver guia).
   Mesma altura das linhas reais para não haver salto quando os resultados chegam.
2. **Imagens**: miniaturas dos resultados 44×56 com `object-fit: contain` sobre `--color-surface-3`
   (sem cortar), `width`/`height` no `<img>`, `loading="lazy"`, `decoding="async"`.

## Pronto quando
- `pnpm --filter @mv/web typecheck` e `pnpm --filter @mv/web test` passam (os 9 do SearchByName).
- Conferiu em http://localhost:3000/search fazendo uma busca real (o worker está rodando, sem
  Firecrawl) — NÃO clique em "Monitorar". Confira também no modal "Buscar por nome" em /products.
- Escreveu `conceitos/tarefas/E-relatorio.md` (arquivos, mudanças, pedidos, "STATUS: PRONTO").
