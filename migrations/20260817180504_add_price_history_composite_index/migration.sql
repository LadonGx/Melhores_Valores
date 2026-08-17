-- CreateIndex
CREATE INDEX "PriceHistory_productId_scrapedAt_idx" ON "PriceHistory"("productId", "scrapedAt");
