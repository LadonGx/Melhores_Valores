# Guia visual — nova aparência do Melhores Valores

Branch: `feat/nova-aparencia`. Referência visual principal: `conceitos/Mix · Dashboard@1x.png`,
`conceitos/Mix · Produtos@1x.png`, `conceitos/Mix · Buscar produto@1x.png`.
Logo escolhido: **1 · Etiqueta** (`conceitos/Logo · 3 conceitos@1x.png`).

## Regras inegociáveis

1. **Só aparência.** Não mude hooks, services, store, chamadas de API, handlers, props públicas de
   componentes compartilhados, validações, textos de erro ou fluxo. Toda função que existe hoje
   continua existindo e acessível (checkboxes, grupos, filtro, promoções, excluir, atualizar preço,
   renomear, modais, histórico).
2. **Permitido** além de CSS: reorganizar JSX/ordem de colunas, trocar wrappers, adicionar ícones
   (`@/components/Icon`), usar `PageHeader`, e elementos **derivados de dados que a página já
   carrega** (ex.: "Destaques" = itens da lista já buscada; saudação por horário). **Nenhuma**
   chamada de API nova, nenhum filtro/busca/toggle novo, nenhuma dependência nova no package.json.
3. **Desempenho:** nada de fonte web, imagem pesada, biblioteca de animação ou blur grande.
   Imagens de produto com `loading="lazy"` e `decoding="async"`, tamanho fixo (sem layout shift).
   Animações só em `transform`/`opacity`.
4. **Testes continuam passando:** `pnpm --filter @mv/web test` e `pnpm --filter @mv/web typecheck`.
   Placeholders, textos e roles de botões usados nos testes **não mudam**.
5. **Só edite os arquivos da sua tarefa.** Os arquivos base (abaixo) são do coordenador — se
   precisar de algo neles, peça; não edite.
6. Não faça commit nem push. Não suba/derrube containers (o worker/beat estão parados de propósito).

## Já pronto (arquivos do coordenador — não editar)

- `src/styles/global.css` — tokens. **Use só variáveis**, nada de hex solto nos módulos.
- `src/components/Logo` — `<Logo />`, `<LogoMark variant="plain|app" />`.
- `src/components/Icon` — `<Icon name="search" size={16} />` (dashboard, list, search, panel, plus, pause,
  refresh, arrowRight, filter, trash, x, check, external, chart, trendDown, tag, alert, layers,
  chevronDown, chevronRight, link). Se faltar um ícone, peça.
- `src/components/PageHeader` — `<PageHeader title subtitle actions />` (H1 30px + ações à direita).
- `Sidebar` (com rail recolhido), `DashboardLayout` (sem barra de topo; conteúdo centralizado com
  `max-width: var(--content-max)`, padding 40/48px), `Button`, `Card`, `Input`, `Table`, `Modal`,
  `Toast`, `Tooltip`, `ConfirmModal`.
- A barra de topo (Header) foi removida: **cada página agora renderiza seu próprio `PageHeader`.**

## Tokens principais

| Uso | Variável |
|---|---|
| Fundo do conteúdo | `--color-bg` |
| Cards / painéis | `--color-surface` + `1px solid var(--color-border)` + `--radius-lg` |
| Hover de linha, input | `--color-surface-2` |
| Placeholder de imagem | `--color-surface-3` |
| Botão primário | `--color-primary` (Button `variant="primary"`) |
| Botão secundário ("Atualizar preço", "Monitorar", "Buscar por nome") | Button `variant="secondary"` |
| Links "Ver →" e destaque lilás | `--color-primary-soft` |
| **Melhor valor / menor preço / promoção** | `--color-accent` (texto) + `--color-accent-tint` (fundo) |
| Selo de loja (Amazon / Mercado Livre) | fundo `--color-badge-bg`, texto `--color-badge-text`, `--radius-pill` |
| Aviso (ML exigindo login, estoque) | `--color-warning-bg` / `--color-warning-border` / `--color-warning` |
| Texto | `--color-text`, `--color-text-muted`, `--color-text-faint` |

## Padrões de componentes

- **Título de página:** `PageHeader`. Subtítulo em `--color-text-muted` 13px.
- **Card de estatística:** número 30px/700 (`font-family: var(--font-display)`), legenda 12px muted,
  padding 22px 24px. Clicável → hover `--color-surface-2` + cursor pointer.
- **Painel de lista** (Card): cabeçalho 60px com título 15px/600 à esquerda e ações à direita;
  linhas de 68–72px separadas por `--color-border`, hover `--color-surface-2`.
- **Linha de produto:** [checkbox] [thumb 34×46, `--radius-sm`, `object-fit: cover`, fundo
  `--color-surface-3` quando sem imagem] [nome 14px/500 + linha secundária 12px muted] … [selo loja]
  [preço 16px/700 `tabular-nums`] [ação "Ver →" lilás ou botão secondary sm].
- **Selo de loja:** `padding: 3px 10px; font-size: 11.5px; font-weight: 500; border-radius: var(--radius-pill)`.
- **Selo "Menor preço" / promoção:** mesmo formato, cores accent.
- **Preço:** sempre `font-variant-numeric: tabular-nums` (classe global `.tabular` disponível).
- **Estados vazios / carregando / erro:** centralizados, 48px de padding, texto muted; erro com botão ghost.
- **Espaçamento vertical entre blocos da página:** 24px. Grid de stats/cards: gap 16px.
- **Responsivo:** abaixo de 900px os grids viram 1–2 colunas; tabelas rolam na horizontal.

## Como validar visualmente

- App: http://localhost:3000 (dev server já rodando, API em :8000 com os dados reais — **só leitura
  de olho**; não clique em Excluir / Atualizar preço / Monitorar em dados reais).
- Compare com os PNGs "Mix ·" em `conceitos/`.

---

## Fase 2 — padrões novos (pedidos do usuário após a 1ª revisão)

### Seleção · Barra flutuante (referência: `conceitos/Seleção · Barra flutuante@1x.png`)
- **Linha selecionada:** cantos arredondados (`--radius-md`), fundo `--color-selection-bg`, borda
  `1px solid var(--color-selection-border)`, "descolada" das bordas do painel (margem lateral ~10px,
  as linhas vizinhas continuam retas). Nada de destaque reto de ponta a ponta.
- **Ações em lote** saem do topo do painel e vão para `<SelectionBar count onClear>` (componente
  pronto em `@/components/SelectionBar`): "N selecionado(s)" | botões pílula | ×.
  Botões: ação principal `variant="primary" size="sm"` com ícone; excluir
  `variant="dangerOutline" size="sm"` com ícone `trash`. Coloque a `SelectionBar` como **último
  filho da página** (ela é `position: sticky; bottom: 24px` dentro da área rolável).
- **"Selecionar todos"** vira um checkbox com texto no cabeçalho do painel (à direita), ligado ao
  mesmo handler de selecionar/desmarcar todos que já existe.
- Todos os handlers existentes continuam os mesmos — só muda onde os botões aparecem.

### Imagens (qualidade)
- Nunca cortar a imagem do produto: **`object-fit: contain`** sobre `--color-surface-3`.
- Miniatura de lista: **44×56** (`width`/`height` no `<img>`), `--radius-sm`, `loading="lazy"`,
  `decoding="async"`. As imagens de origem têm 300–560px, então não há perda por resolução.
- Imagens maiores (cards/modais): no mínimo 140px de altura de área de imagem.

### Esqueletos de carregamento
- Bloco com `background: var(--color-surface-2)` (ou `--color-surface-3` para a área de imagem),
  `--radius-sm`, animação **só de opacity**: `@keyframes pulse { 50% { opacity: .55 } }`, 1.4s.
- Mesmas dimensões do conteúdo real (evita layout shift). `aria-hidden="true"` nos esqueletos.
