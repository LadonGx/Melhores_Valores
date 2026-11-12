-- Quem vendia a oferta em cada leitura de preço (Amazon ou terceiros), para separar os
-- preços de terceiros sem descartá-los. Registros antigos ficam nulos (não identificado).
-- AlterTable
ALTER TABLE "PriceHistory" ADD COLUMN     "sellerName" TEXT,
ADD COLUMN     "sellerType" TEXT;
