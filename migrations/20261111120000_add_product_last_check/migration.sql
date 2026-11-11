-- Quando o produto foi verificado de verdade (o histórico de preços é deduplicado e não serve para isso).
-- AlterTable
ALTER TABLE "Product" ADD COLUMN     "lastAttemptAt" TIMESTAMP(3),
ADD COLUMN     "lastCheckError" TEXT,
ADD COLUMN     "lastCheckStatus" TEXT,
ADD COLUMN     "lastCheckedAt" TIMESTAMP(3);

-- Produtos já monitorados: a última leitura gravada no histórico é a melhor estimativa
-- da última verificação (lastCheckStatus fica NULL: não há como saber o resultado).
UPDATE "Product" AS p
SET "lastCheckedAt" = h."lastScrapedAt",
    "lastAttemptAt" = h."lastScrapedAt"
FROM (
    SELECT "productId", MAX("scrapedAt") AS "lastScrapedAt"
    FROM "PriceHistory"
    GROUP BY "productId"
) AS h
WHERE h."productId" = p."id";
