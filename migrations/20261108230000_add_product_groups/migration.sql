-- CreateTable
CREATE TABLE "ProductGroup" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ProductGroup_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ProductGroupItem" (
    "groupId" TEXT NOT NULL,
    "productId" TEXT NOT NULL,

    CONSTRAINT "ProductGroupItem_pkey" PRIMARY KEY ("groupId","productId")
);

-- CreateIndex
CREATE INDEX "ProductGroupItem_productId_idx" ON "ProductGroupItem"("productId");

-- AddForeignKey
ALTER TABLE "ProductGroupItem" ADD CONSTRAINT "ProductGroupItem_groupId_fkey" FOREIGN KEY ("groupId") REFERENCES "ProductGroup"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ProductGroupItem" ADD CONSTRAINT "ProductGroupItem_productId_fkey" FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE CASCADE ON UPDATE CASCADE;
