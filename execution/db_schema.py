"""
Schema do SQLite, versionado por `PRAGMA user_version`.

Cada item de MIGRATIONS leva o banco da versão i para i + 1. Para mudar o
schema, adicione um novo item ao final; nunca edite um item que já foi lançado.
Datas são gravadas como texto ISO 8601 em UTC (ver db_client._iso).
"""

MIGRATIONS: list[str] = [
    # v1: equivalente às 3 migrations do Prisma (Postgres) da branch main
    """
    CREATE TABLE Product (
        id        TEXT PRIMARY KEY,
        url       TEXT NOT NULL UNIQUE,
        name      TEXT,
        imageUrl  TEXT,
        store     TEXT NOT NULL,
        status    TEXT NOT NULL DEFAULT 'active',
        createdAt TEXT NOT NULL,
        updatedAt TEXT NOT NULL
    );

    CREATE TABLE PriceHistory (
        id        TEXT PRIMARY KEY,
        price     REAL,
        inStock   INTEGER NOT NULL DEFAULT 1,
        scrapedAt TEXT NOT NULL,
        productId TEXT NOT NULL REFERENCES Product(id) ON DELETE CASCADE
    );

    CREATE INDEX PriceHistory_productId_scrapedAt_idx ON PriceHistory(productId, scrapedAt);

    CREATE TABLE SearchResult (
        id           TEXT PRIMARY KEY,
        search_id    TEXT NOT NULL,
        query        TEXT NOT NULL,
        store        TEXT NOT NULL,
        title        TEXT NOT NULL,
        price        REAL,
        currency     TEXT NOT NULL DEFAULT 'BRL',
        image_url    TEXT,
        product_url  TEXT NOT NULL,
        rating       REAL,
        review_count INTEGER,
        found_at     TEXT NOT NULL
    );

    CREATE INDEX SearchResult_search_id_idx ON SearchResult(search_id);
    CREATE INDEX SearchResult_query_store_idx ON SearchResult(query, store);
    """,
    # v2: estado interno do app (ex: horário da última checagem completa,
    # usado pelo agendador para recuperar rodadas perdidas com o app fechado)
    """
    CREATE TABLE AppMeta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # v3: grupos de produtos (antes ficavam só no localStorage do frontend, fora
    # do backup do banco e sujeitos a sumir se os dados da janela fossem limpos).
    # Membro some sozinho quando o produto é excluído (CASCADE).
    """
    CREATE TABLE ProductGroup (
        id        TEXT PRIMARY KEY,
        name      TEXT NOT NULL,
        createdAt TEXT NOT NULL
    );

    CREATE TABLE ProductGroupMember (
        groupId   TEXT NOT NULL REFERENCES ProductGroup(id) ON DELETE CASCADE,
        productId TEXT NOT NULL REFERENCES Product(id) ON DELETE CASCADE,
        position  INTEGER NOT NULL,
        PRIMARY KEY (groupId, productId)
    );

    CREATE INDEX ProductGroupMember_productId_idx ON ProductGroupMember(productId);
    """,
]
