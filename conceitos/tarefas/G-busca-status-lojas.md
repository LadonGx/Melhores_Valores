# Tarefa G — Busca: status das lojas no lugar do aviso solto + convite inicial (agente OpenCode)

Leia `D:\Estudos\Melhores_Valores\conceitos\GUIA_VISUAL.md` (fase 1 e "Fase 2"). Branch
`feat/nova-aparencia`. Regras: testes passando (`SearchByName.test.tsx` intocado), **sem commit**.

## ⚠️ DADOS DO USUÁRIO — PROIBIDO APAGAR
Nunca exclua produtos/histórico/grupos, nem clique em "Monitorar" (isso grava no banco). Buscas
podem ser feitas (não salvam produtos). Estados especiais → interceptação de rede no Playwright
(`page.route("**/api/stores/health", ...)`), em navegador separado, prints no seu scratchpad.

## Seus arquivos
- `apps/web/src/features/search/components/SearchByName.tsx` / `.module.css`
- `apps/web/src/pages/Search/index.tsx` / `Search.module.css`

## Já pronto para usar (do coordenador — não editar)
- `useStoresHealth()` e `storesHealthKey` em `@/features/stores/hooks/useStoresHealth`
- `<StoreStatusDot status />` e `STORE_STATUS_LABEL` em `@/features/stores/components/StoreStatusDot`
- Tipos `StoreHealth`, `StoreChannelHealth` em `@mv/types`. Resposta de `GET /api/stores/health`:
  `{ stores: [{ store, label, status: ok|partial|blocked|error|unknown,
     channels: { search: {status, detail, last_ok_at, last_fail_at}, monitor: {...} } }] }`
  `channels.search` = busca por nome; `channels.monitor` = verificação de preço dos anúncios.

## O que fazer
1. **Linha de status das lojas** logo abaixo do formulário de busca (página e modal):
   `● Amazon · busca funcionando   ● Mercado Livre · busca exigindo login` — usando
   `StoreStatusDot` com o status do **canal search** e o `detail`. Discreta (12.5px, muted).
   Se a API de saúde falhar ou estiver carregando, não mostrar nada (sem quebrar a busca).
2. **Aviso de loja bloqueada explicado** (o que hoje é o banner solto): quando a busca retornar
   `warnings` de uma loja, o banner passa a explicar o impacto usando o canal monitor:
   - monitor ok → "**Mercado Livre está exigindo login para buscas automáticas.** Os resultados
     abaixo vêm das outras lojas. Os anúncios do Mercado Livre que você já monitora continuam
     sendo verificados normalmente."
   - monitor com problema → "...Os anúncios do Mercado Livre que você monitora também estão com
     falha na verificação de preço."
   - Mantenha a palavra-chave do texto atual se algum teste a usar (confira o arquivo de teste).
3. Quando uma busca termina, invalide `storesHealthKey` (via `useQueryClient`) para a sidebar e a
   linha de status atualizarem na hora — é a ÚNICA alteração de comportamento permitida.
4. **Convite inicial** (antes da primeira busca, sem resultados): bloco leve abaixo do formulário,
   "Comece pelo nome do produto" + 3 exemplos clicáveis como chips que só **preenchem** o campo
   (ex.: "Kindle Paperwhite", "Echo Dot", "20th Century Boys") — sem disparar a busca. Use
   `<button type="button">` e garanta que os testes que contam botões continuem passando
   (o convite NÃO aparece durante o loading). No modal "Buscar por nome"
   (em /products) o convite também deve ficar bom.
5. Estado "nenhum resultado": convite para tentar outro termo/ajustar faixa de preço.

## Pronto quando
- `pnpm --filter @mv/web typecheck` e `pnpm --filter @mv/web test` passam.
- Prints: busca inicial, carregando, resultados com ML bloqueado, e linha de status
  (incluindo um caso simulado por interceptação com monitor do ML em erro).
- `conceitos/tarefas/G-relatorio.md` (arquivos, decisões, caminhos dos prints, "STATUS: PRONTO").
