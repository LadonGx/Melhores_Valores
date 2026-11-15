-- Formato do anúncio (ebook_kindle | physical); os antigos ficam NULL até a próxima checagem bem-sucedida.
-- AlterTable
ALTER TABLE "Product" ADD COLUMN     "format" TEXT;

-- Uma linha por checagem real, para medir a taxa de sucesso por loja (GET /stores/stats).
-- CreateTable
CREATE TABLE "CheckAttempt" (
    "id" TEXT NOT NULL,
    "productId" TEXT NOT NULL,
    "store" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "blockCategory" TEXT,
    "error" TEXT,
    "level" INTEGER,
    "durationMs" INTEGER,
    "trigger" TEXT NOT NULL DEFAULT 'scheduled',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "CheckAttempt_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "CheckAttempt_store_createdAt_idx" ON "CheckAttempt"("store", "createdAt");

-- CreateIndex
CREATE INDEX "CheckAttempt_productId_createdAt_idx" ON "CheckAttempt"("productId", "createdAt");

-- AddForeignKey
ALTER TABLE "CheckAttempt" ADD CONSTRAINT "CheckAttempt_productId_fkey" FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE CASCADE ON UPDATE CASCADE;
