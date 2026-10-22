# Diretiva 01: Banco de Dados (SQLite)

> Na branch `exe` o banco deixou de ser PostgreSQL via Prisma e passou a ser um arquivo SQLite local (ver `docs/plano-executavel.md`, Fase 2). O nome do arquivo foi mantido para não quebrar links.

- **Arquivo:** `melhores_valores.db` na pasta de dados do usuário (`%LOCALAPPDATA%\MelhoresValores\` no Windows). `MV_DATA_DIR` troca a pasta (dev/testes).
- **Único ponto de acesso:** `execution/db_client.py`. Nenhum outro módulo abre conexão ou escreve SQL.
- **Schema:** `execution/db_schema.py`. Cada item de `MIGRATIONS` leva o banco de uma versão para a próxima (`PRAGMA user_version`); as migrações rodam sozinhas na primeira conexão. Para mudar o schema, **adicione** um item novo ao final; nunca edite um que já foi lançado (os usuários já têm bancos naquela versão).
- **Modelos:** `execution/models.py` (Pydantic, mesmos nomes de campo que o Prisma usava). Campo novo no banco = campo novo no modelo.
- **Datas:** sempre texto ISO 8601 em UTC (`db_client._iso`). A ordenação e os filtros por data comparam texto, então o formato precisa ser único.
- **Concorrência:** uma conexão por thread, modo WAL, escritas serializadas por `_write()` (lock + transação).
- **Testes:** `execution/tests/test_db_client_sqlite.py` roda contra um banco real em `tmp_path`, sem Docker.
