-- Cada anúncio fica em no máximo um grupo.

-- Se algum anúncio já estiver em mais de um grupo, mantém só no grupo mais antigo
DELETE FROM "ProductGroupItem" AS i
USING "ProductGroup" AS g, "ProductGroupItem" AS other, "ProductGroup" AS og
WHERE g."id" = i."groupId"
  AND other."productId" = i."productId"
  AND og."id" = other."groupId"
  AND (og."createdAt", og."id") < (g."createdAt", g."id");

-- Grupos que ficaram com menos de 2 anúncios são desfeitos
DELETE FROM "ProductGroup"
WHERE "id" IN (
    SELECT g."id"
    FROM "ProductGroup" AS g
    LEFT JOIN "ProductGroupItem" AS i ON i."groupId" = g."id"
    GROUP BY g."id"
    HAVING COUNT(i."productId") < 2
);

-- DropIndex
DROP INDEX "ProductGroupItem_productId_idx";

-- CreateIndex
CREATE UNIQUE INDEX "ProductGroupItem_productId_key" ON "ProductGroupItem"("productId");
