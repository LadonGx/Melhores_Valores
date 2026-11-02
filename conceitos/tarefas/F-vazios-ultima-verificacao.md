# Tarefa F — Listas vazias com convite + "última verificação" em cada item (agente Claude)

Leia `D:\Estudos\Melhores_Valores\conceitos\GUIA_VISUAL.md` (fase 1 e "Fase 2"). Branch
`feat/nova-aparencia`. Regras: não mexer em hooks/services/API existentes, testes passando,
**sem commit**, e **sem trailer Co-Authored-By** se algum dia for pedir commit.

## ⚠️ DADOS DO USUÁRIO — PROIBIDO APAGAR
**Nunca** exclua produtos, grupos, histórico ou qualquer dado (nem pela UI, nem pela API, nem no
banco, nem no localStorage) — nem "para testar". Para ver os estados vazios use **interceptação de
rede** num navegador separado, por exemplo Playwright com o Chrome instalado:
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1568, "height": 698})
    pg.route("**/api/products", lambda r: r.fulfill(json={"total": 0, "products": []}))
    pg.goto("http://localhost:3000/"); pg.screenshot(path="...png")
```
(salve scripts/prints no seu scratchpad, não no repositório) — ou testes unitários com mocks.

## Seus arquivos
- NOVO `apps/web/src/components/EmptyState/` (index.tsx + module.css)
- NOVO `apps/web/src/features/products/formatLastChecked.ts` (+ `.test.ts`)
- `apps/web/src/pages/Dashboard/index.tsx` / `Dashboard.module.css`
- `apps/web/src/pages/Products/index.tsx` / `Products.module.css`
(O coordenador mexe na Sidebar e em `features/stores`; o OpenCode mexe na Busca. Não toque neles.)

## 1. EmptyState (componente compartilhado)
Props: `icon?` (default `<LogoMark variant="app" size={44} />`), `title`, `description`, `actions?`.
Centralizado, padding ~56px, título 17px/700, descrição muted 13.5px máx. 420px, ações em linha.
Visual calmo (sem ilustração pesada; só o símbolo do logo).

## 2. Listas vazias com convite
- **Dashboard** sem produtos (hoje: texto + link): `EmptyState` "Nenhum produto monitorado ainda" /
  "Busque pelo nome ou cole o link de um anúncio da Amazon ou do Mercado Livre — a gente avisa
  quando o preço cair." Ações: **Buscar produto** (primary → `/search`) e **Adicionar por URL**
  (secondary → `/products?adicionar=url`).
- **Dashboard com filtro escondendo tudo** ("Nenhum produto corresponde ao filtro atual"):
  `EmptyState` compacto com botão **Mostrar todos** chamando o `showAll` que já existe.
- **Produtos** sem produtos: em vez da Table com mensagem, `EmptyState` com as mesmas ações
  ("Buscar por nome" abre o modal de busca que já existe; "+ Adicionar URL" abre o modal de URL).
- **Produtos** deve abrir o modal "Adicionar produto por URL" quando a URL tiver
  `?adicionar=url` (lê com `useSearchParams` uma vez e limpa o parâmetro ao abrir).
- Esconder a `SelectionBar`/"Selecionar todos" quando a lista está vazia (se ainda não acontece).

## 3. "Última verificação" em cada item
- `formatLastChecked(iso, now)` → `"há 5 min"`, `"há 3 h"`, `"ontem, 18:41"`, `"28/10, 20:51"`;
  e `isStale(iso, now)` = mais de 12 h (2 ciclos de 6 h do agendamento automático perdidos).
  Testes unitários para os dois.
- **Dashboard (ProductRow):** troque "Verificado em 01/11/2026, 18:41" por
  "Verificado há 3 h" (com `title` mostrando a data completa). Se `isStale`, texto em
  `--color-warning` + ícone `alert` 12px e title "Sem verificação há mais de 12 h".
- **Dashboard (GroupRow):** mostrar a verificação mais recente entre os anúncios do grupo,
  no mesmo formato, junto do "N anúncios".
- **Produtos:** nova linha secundária sob o domínio da URL **ou** troque a coluna "Adicionado em"
  por "Última verificação" (mantendo "Adicionado em" no `title`) — escolha o que ficar mais limpo
  e explique no relatório. Mesmo formato/estado "stale".
- Produto sem `last_checked`: "Ainda não verificado" (faint).

## Pronto quando
- `pnpm --filter @mv/web typecheck` e `pnpm --filter @mv/web test` passam.
- Prints conferidos: Dashboard e Produtos com dados reais **e** vazios (via interceptação).
- `conceitos/tarefas/F-relatorio.md` com arquivos, decisões, prints (caminhos) e "STATUS: PRONTO".
