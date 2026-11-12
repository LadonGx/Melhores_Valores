# Revisão de preços da Amazon (leitor pegava preço de carrossel)

## O que estava errado

O adapter da Amazon (`execution/adapters/amazon.py`) procurava `span.a-price` na **página inteira**
(Estratégias 1 e 4 de `_extract_price_from_soup`). Quando o anúncio não tem uma oferta principal
na caixa de compra, o primeiro `span.a-price` da página era de um **carrossel de recomendações ou
patrocinados** (`#sp_detail`, `sims-*`, `CardInstance…`), e esse preço era gravado como se fosse
do produto.

Casos confirmados com o HTML real das páginas:

| ASIN | Produto | Preço gravado (errado) | Preço correto |
|---|---|---|---|
| `6525954525` | 20th Century Boys 07 | R$ 52,40 (card de `#sp_detail`/`sims-*`) e R$ 37,31 | Sem oferta principal: só outros vendedores, "Capa Comum a partir de R$ 78,90" |
| `B0FYGGWCHR` | Ritmo da Guerra (Kindle) | R$ 92,90 (um `CardInstance…` de recomendação) | R$ 84,71 (botão Kindle selecionado em `#tmmSwatches`) |

Os outros 14 anúncios conferidos estavam corretos e continuam com o mesmo preço.

## O que mudou no leitor

- O preço só é lido das áreas de preço **do produto** (`#corePrice_feature_div`,
  `#corePriceDisplay_desktop_feature_div`, `#apex_desktop*`, `#mediaTab_heading_0`) e do botão de
  formato selecionado em `#tmmSwatches`. Nada de carrossel.
- Sem oferta principal, o leitor não inventa preço: devolve o "a partir de" do formato selecionado
  (`offer_type: "third_party_from"`, confiança 0,6) ou, se nem isso existir e a página mostrar
  só "Ver todas as opções de compra", `price: None` com `offer_type: "none"`. O pipeline trata esse caso como `no_offer` (não grava histórico).

## SQL de revisão (homelab)

> **Nada disto foi executado.** Rode no Postgres do homelab (por exemplo
> `docker compose exec db psql -U <usuario> -d price_tracker`) depois de fazer backup
> (`pg_dump`). Confira os `SELECT`s antes de apagar qualquer coisa.

Produtos envolvidos: `40c6ded9-bf0d-4bd0-84c3-00a3345dad4c` (6525954525) e o produto cujo `url`
contém `B0FYGGWCHR`.

### 1. Conferir os produtos e o que está gravado

```sql
-- Os dois produtos
SELECT "id", "name", "store", "url"
FROM "Product"
WHERE "id" = '40c6ded9-bf0d-4bd0-84c3-00a3345dad4c'
   OR "url" ILIKE '%B0FYGGWCHR%';

-- Histórico completo dos dois, agrupado por preço (primeira e última vez em que cada preço apareceu)
SELECT p."url", h."price", h."inStock",
       COUNT(*)           AS linhas,
       MIN(h."scrapedAt") AS primeira_vez,
       MAX(h."scrapedAt") AS ultima_vez
FROM "PriceHistory" h
JOIN "Product" p ON p."id" = h."productId"
WHERE p."id" = '40c6ded9-bf0d-4bd0-84c3-00a3345dad4c'
   OR p."url" ILIKE '%B0FYGGWCHR%'
GROUP BY p."url", h."price", h."inStock"
ORDER BY p."url", MIN(h."scrapedAt");

-- Exatamente as linhas que seriam apagadas (devem ser só preços de carrossel)
SELECT h."id", p."url", h."price", h."inStock", h."scrapedAt"
FROM "PriceHistory" h
JOIN "Product" p ON p."id" = h."productId"
WHERE (p."id" = '40c6ded9-bf0d-4bd0-84c3-00a3345dad4c' AND h."price" IN (37.31, 52.40))
   OR (p."url" ILIKE '%B0FYGGWCHR%' AND h."price" = 92.90)
ORDER BY p."url", h."scrapedAt";
```

### 2. Apagar as linhas erradas (dentro de uma transação que desfaz tudo)

```sql
BEGIN;

DELETE FROM "PriceHistory" h
USING "Product" p
WHERE p."id" = h."productId"
  AND (
        (p."id" = '40c6ded9-bf0d-4bd0-84c3-00a3345dad4c' AND h."price" IN (37.31, 52.40))
     OR (p."url" ILIKE '%B0FYGGWCHR%' AND h."price" = 92.90)
  );
-- Esperado: o mesmo número de linhas do último SELECT da etapa 1.

-- Conferir como ficou o histórico dos dois produtos
SELECT p."url", h."price", h."inStock", h."scrapedAt"
FROM "PriceHistory" h
JOIN "Product" p ON p."id" = h."productId"
WHERE p."id" = '40c6ded9-bf0d-4bd0-84c3-00a3345dad4c'
   OR p."url" ILIKE '%B0FYGGWCHR%'
ORDER BY p."url", h."scrapedAt";

ROLLBACK;  -- troque por COMMIT; só depois de aprovar o resultado acima
```

### Critério e riscos

- **Critério:** só saem linhas de `PriceHistory` desses dois produtos cujo preço é um dos valores de
  carrossel já identificados no HTML real (37,31 e 52,40 no primeiro; 92,90 no segundo). Nenhuma
  outra linha, nenhum outro produto, e o `Product` em si não é tocado.
- **Risco 1 — preço coincidente:** se o anúncio chegou a custar de verdade exatamente esse valor em
  algum momento, a linha legítima também seria apagada. Por isso o SELECT de conferência mostra
  datas e quantidade: o esperado é que as linhas apareçam em sequência desde que o produto foi
  cadastrado, sem relação com mudanças reais de preço.
- **Risco 2 — não há como recuperar** depois do `COMMIT`; faça o `pg_dump` antes.
- **Risco 3 — leituras erradas com outros valores:** o leitor antigo pode ter gravado outros preços
  de carrossel que não estão na lista (cada recomendação muda com o tempo). Se a etapa 1 mostrar
  outros valores suspeitos, inclua-os na lista de forma explícita; não use faixas de preço.
- **Fora de estoque:** linhas com `price` nulo (`inStock = false`) não são tocadas.
- Depois de apagar, os próximos ciclos de checagem voltam a gravar o preço correto (84,71 no Kindle;
  para o 6525954525, o "a partir de" de R$ 78,90 ou nenhuma linha, se não houver oferta).

### 3. (Opcional) Marcar como terceiros as leituras "a partir de" gravadas antes da coluna de vendedor

A partir da migração `add_price_history_seller`, cada leitura grava quem vendia (`sellerType`).
Leituras do 6525954525 feitas pela versão anterior (com o "a partir de" de R$ 78,90, mas ainda sem
vendedor) ficam com `sellerType` nulo e entram nas estatísticas como se fossem da Amazon. Para
corrigir só elas:

```sql
BEGIN;

-- Conferir: devem ser só leituras de 78,90 a partir de 11/11/2026, sem vendedor
SELECT "id", "price", "sellerType", "scrapedAt"
FROM "PriceHistory"
WHERE "productId" = '40c6ded9-bf0d-4bd0-84c3-00a3345dad4c'
  AND "sellerType" IS NULL
  AND "price" = 78.90
  AND "scrapedAt" >= '2026-11-11';

UPDATE "PriceHistory"
SET "sellerType" = 'third_party_from'
WHERE "productId" = '40c6ded9-bf0d-4bd0-84c3-00a3345dad4c'
  AND "sellerType" IS NULL
  AND "price" = 78.90
  AND "scrapedAt" >= '2026-11-11';

ROLLBACK;  -- troque por COMMIT; se o SELECT mostrou só as linhas esperadas
```

Leituras antigas de outros anúncios que já eram de terceiros na caixa de compra (ex.: B0FWQX18JQ,
6525949394) não têm como ser identificadas depois do fato: continuam com vendedor nulo.
