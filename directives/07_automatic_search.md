# 🤖 Prompt de Implementação: Feature de Busca Automática de Produtos

> **Versão:** 2.0 — Alinhado com a arquitetura real do projeto  
> **Projeto:** Price Tracker (Melhores Valores)  
> **Diretiva de referência:** `directives/07_automatic_search.md`  
> **Status da feature:** ❌ Pendente de implementação

---

## 📌 Contexto e Regras Obrigatórias

Antes de escrever qualquer código, leia obrigatoriamente:

- `directives/04_adapters_pattern.md` — padrão de adapters que deve ser seguido
- `directives/05_caching_rules.md` — regra Cache-First obrigatória
- `directives/07_automatic_search.md` — especificação completa desta feature

### Restrições de arquitetura que DEVEM ser respeitadas:

1. **`db_client.py` é a única interface com o banco.** Nunca chame o cliente Prisma diretamente em outro arquivo. Toda nova operação de banco deve ser uma nova função em `db_client.py`.
2. **O cliente Prisma é síncrono** (`prisma-client-python 0.11.0`). Não use `await` nas chamadas ao banco.
3. **Não modifique nenhum arquivo existente além dos indicados neste prompt.** Apenas `schema.prisma`, `db_client.py`, `worker_tasks.py` e `web_server.py` devem ser alterados.
4. **Não adicione novas dependências ao `requirements.txt`.** Todas as bibliotecas necessárias (`httpx`, `beautifulsoup4`, `lxml`) já estão instaladas.

---

## 🗄️ PASSO 1 — Atualizar `schema.prisma`

Adicione o model abaixo **ao final** do arquivo `schema.prisma`, após os models existentes (`Product` e `PriceHistory`):

```prisma
model SearchResult {
  id           String   @id @default(uuid())
  search_id    String
  query        String
  store        String
  title        String
  price        Float?
  currency     String   @default("BRL")
  image_url    String?
  product_url  String
  rating       Float?
  review_count Int?
  found_at     DateTime @default(now())

  @@index([search_id])
  @@index([query, store])
}
```

Após salvar, execute os comandos de migração:

```bash
prisma migrate dev --name add_search_results
prisma generate
```

---

## 🐍 PASSO 2 — Adicionar funções em `execution/db_client.py`

**Motivo:** `db_client.py` é a única interface com o banco no projeto. Seguindo o padrão já existente das funções `get_or_create_product`, `add_price_history`, etc., adicione as duas funções abaixo **ao final do arquivo**, antes de qualquer bloco `if __name__ == "__main__"`, se existir.

```python
# ─────────────────────────────────────────────
# SearchResult — Busca automática de produtos
# ─────────────────────────────────────────────

def save_search_results(search_id: str, query: str, results: list[dict]) -> int:
    """
    Persiste a lista de resultados de busca no banco de dados.
    Segue o padrão síncrono do projeto (prisma-client-python).

    Args:
        search_id: UUID que agrupa todos os resultados desta busca.
        query: Termo buscado pelo usuário (ex: "iPhone 15").
        results: Lista de dicts normalizados retornados pelos search_scrapers.

    Returns:
        Número de registros salvos com sucesso.
    """
    saved = 0
    for item in results:
        try:
            db.searchresult.create(data={
                "search_id":    search_id,
                "query":        query,
                "store":        item["store"],
                "title":        item["title"],
                "price":        item.get("price"),
                "currency":     item.get("currency", "BRL"),
                "image_url":    item.get("image_url"),
                "product_url":  item["product_url"],
                "rating":       item.get("rating"),
                "review_count": item.get("review_count"),
            })
            saved += 1
        except Exception as e:
            print(f"[db_client] Erro ao salvar SearchResult: {e}")
            continue
    return saved


def get_search_results(search_id: str) -> list:
    """
    Retorna todos os resultados de uma busca ordenados pelo menor preço.

    Args:
        search_id: UUID da busca a ser consultada.

    Returns:
        Lista de SearchResult ordenada por preço ascendente.
        Resultados sem preço (None) aparecem ao final.
    """
    try:
        return db.searchresult.find_many(
            where={"search_id": search_id},
            order={"price": "asc"},
        )
    except Exception as e:
        print(f"[db_client] Erro ao buscar SearchResults: {e}")
        return []
```

---

## 📁 PASSO 3 — Criar a pasta `execution/search_scrapers/`

Crie a pasta e os 4 arquivos a seguir:

---

### `execution/search_scrapers/__init__.py`

```python
# search_scrapers package
```

---

### `execution/search_scrapers/amazon_search.py`

**Motivo:** Faz scraping da página de resultados da Amazon BR via `httpx` + `BeautifulSoup`. A Amazon renderiza os cards de produto no HTML estático da página de busca, dispensando Playwright. Segue o mesmo padrão do `base_scraper.py` já existente no projeto (pool de User-Agents rotacionados).

```python
import httpx
from bs4 import BeautifulSoup
import random

HEADERS_POOL = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    },
]

def search_amazon(query: str, max_results: int = 10) -> list[dict]:
    """
    Busca produtos na Amazon BR pela página de resultados.
    Retorna lista normalizada de dicts prontos para salvar via db_client.
    """
    url = f"https://www.amazon.com.br/s?k={query.replace(' ', '+')}"
    results = []

    try:
        headers = random.choice(HEADERS_POOL)
        with httpx.Client(timeout=15, headers=headers, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        items = soup.select("div[data-component-type='s-search-result']")

        for item in items[:max_results]:
            try:
                title_el    = item.select_one("h2 a span")
                link_el     = item.select_one("h2 a")
                price_whole = item.select_one("span.a-price-whole")
                price_frac  = item.select_one("span.a-price-fraction")
                image_el    = item.select_one("img.s-image")
                rating_el   = item.select_one("span.a-icon-alt")
                reviews_el  = item.select_one("span.a-size-base.s-underline-text")

                if not title_el or not link_el:
                    continue

                price = None
                if price_whole:
                    whole = price_whole.get_text(strip=True).replace(".", "").replace(",", "")
                    frac  = price_frac.get_text(strip=True) if price_frac else "00"
                    try:
                        price = float(f"{whole}.{frac}")
                    except Exception:
                        pass

                rating = None
                if rating_el:
                    try:
                        rating = float(rating_el.get_text(strip=True).split(" ")[0].replace(",", "."))
                    except Exception:
                        pass

                reviews = None
                if reviews_el:
                    try:
                        reviews = int(reviews_el.get_text(strip=True).replace(".", "").replace(",", ""))
                    except Exception:
                        pass

                results.append({
                    "store":        "amazon",
                    "title":        title_el.get_text(strip=True),
                    "product_url":  "https://www.amazon.com.br" + link_el.get("href", ""),
                    "price":        price,
                    "currency":     "BRL",
                    "image_url":    image_el.get("src") if image_el else None,
                    "rating":       rating,
                    "review_count": reviews,
                })
            except Exception:
                continue

    except Exception as e:
        print(f"[amazon_search] Erro: {e}")

    return results
```

---

### `execution/search_scrapers/mercadolivre_search.py`

**Motivo:** Faz scraping da listagem de busca do Mercado Livre. A página de resultados do ML renderiza os cards no HTML, funcionando com `httpx` simples. Usa os mesmos seletores CSS do `mercadolivre.py` (adapter existente).

```python
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

def search_mercadolivre(query: str, max_results: int = 10) -> list[dict]:
    """
    Busca produtos no Mercado Livre BR pela página de listagem.
    Retorna lista normalizada de dicts prontos para salvar via db_client.
    """
    url = f"https://lista.mercadolivre.com.br/{query.replace(' ', '-')}"
    results = []

    try:
        with httpx.Client(timeout=15, headers=HEADERS, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        items = soup.select("li.ui-search-layout__item")

        for item in items[:max_results]:
            try:
                link_el    = item.select_one("a.poly-component__title")
                price_int  = item.select_one("span.andes-money-amount__integer")
                price_frac = item.select_one("span.andes-money-amount__fraction")
                image_el   = item.select_one("img.poly-component__picture")
                rating_el  = item.select_one("span.poly-reviews__rating")
                reviews_el = item.select_one("span.poly-reviews__total")

                if not link_el:
                    continue

                price = None
                if price_int:
                    whole = price_int.get_text(strip=True).replace(".", "").replace(",", "")
                    frac  = price_frac.get_text(strip=True) if price_frac else "00"
                    try:
                        price = float(f"{whole}.{frac}")
                    except Exception:
                        pass

                rating = None
                if rating_el:
                    try:
                        rating = float(rating_el.get_text(strip=True).replace(",", "."))
                    except Exception:
                        pass

                reviews = None
                if reviews_el:
                    try:
                        reviews = int(reviews_el.get_text(strip=True).strip("()").replace(".", ""))
                    except Exception:
                        pass

                results.append({
                    "store":        "mercadolivre",
                    "title":        link_el.get_text(strip=True),
                    "product_url":  link_el.get("href", ""),
                    "price":        price,
                    "currency":     "BRL",
                    "image_url":    image_el.get("src") or image_el.get("data-src") if image_el else None,
                    "rating":       rating,
                    "review_count": reviews,
                })
            except Exception:
                continue

    except Exception as e:
        print(f"[mercadolivre_search] Erro: {e}")

    return results
```

---

### `execution/search_scrapers/shopee_search.py`

**Motivo:** A Shopee expõe uma API interna JSON que retorna os produtos de busca estruturados. Isso é mais estável que scraping de HTML (sem seletores CSS para quebrar) e não requer Playwright. O preço vem em centavos × 100.000 e é convertido para float.

```python
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer":          "https://shopee.com.br/",
    "X-Requested-With": "XMLHttpRequest",
}

def search_shopee(query: str, max_results: int = 10) -> list[dict]:
    """
    Busca produtos na Shopee BR via API interna JSON.
    Mais estável que scraping de HTML — dados chegam estruturados.
    Retorna lista normalizada de dicts prontos para salvar via db_client.
    """
    url = "https://shopee.com.br/api/v4/search/search_items"
    params = {
        "by":        "relevancy",
        "keyword":   query,
        "limit":     max_results,
        "newest":    0,
        "order":     "desc",
        "page_type": "search",
    }
    results = []

    try:
        with httpx.Client(timeout=15, headers=HEADERS) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        items = data.get("items") or []

        for item in items[:max_results]:
            try:
                info      = item.get("item_basic", {})
                shop_id   = info.get("shopid")
                item_id   = info.get("itemid")
                name      = info.get("name", "")
                price_raw = info.get("price")        # centavos × 100.000
                image_id  = info.get("image", "")
                rating_obj = info.get("item_rating", {})

                if not name:
                    continue

                price       = round(price_raw / 100000, 2) if price_raw else None
                image_url   = f"https://cf.shopee.com.br/file/{image_id}" if image_id else None
                product_url = f"https://shopee.com.br/product/{shop_id}/{item_id}"
                rating      = rating_obj.get("rating_star")

                review_count_raw = rating_obj.get("rating_count", [0])
                total_reviews = (
                    sum(review_count_raw)
                    if isinstance(review_count_raw, list)
                    else review_count_raw
                )

                results.append({
                    "store":        "shopee",
                    "title":        name,
                    "product_url":  product_url,
                    "price":        price,
                    "currency":     "BRL",
                    "image_url":    image_url,
                    "rating":       rating,
                    "review_count": total_reviews,
                })
            except Exception:
                continue

    except Exception as e:
        print(f"[shopee_search] Erro: {e}")

    return results
```

---

## 📁 PASSO 4 — Criar `execution/search_orchestrator.py`

**Motivo:** Segue o mesmo padrão do `scraping_orchestrator.py` já existente — um módulo central que coordena múltiplos scrapers e delega a persistência ao `db_client.py`. Não acessa o banco diretamente.

```python
import uuid

from execution.search_scrapers.amazon_search       import search_amazon
from execution.search_scrapers.mercadolivre_search import search_mercadolivre
from execution.search_scrapers.shopee_search       import search_shopee
from execution.db_client                           import save_search_results

SEARCH_FUNCTIONS = [
    search_amazon,
    search_mercadolivre,
    search_shopee,
]

def run_product_search(query: str) -> str:
    """
    Executa a busca por nome do produto nas 3 lojas e persiste os resultados.

    Fluxo:
        1. Gera um search_id único para agrupar os resultados desta busca
        2. Chama cada scraper de busca (Amazon, Mercado Livre, Shopee)
        3. Agrega todos os resultados normalizados
        4. Delega a persistência ao db_client (única interface com o banco)
        5. Retorna o search_id para o cliente consultar via GET /search/{id}

    Args:
        query: Termo de busca informado pelo usuário (ex: "iPhone 15 128GB").

    Returns:
        search_id (UUID string) para consulta posterior dos resultados.
    """
    search_id   = str(uuid.uuid4())
    all_results = []

    for search_fn in SEARCH_FUNCTIONS:
        try:
            results = search_fn(query, max_results=10)
            all_results.extend(results)
            print(f"[search_orchestrator] {search_fn.__name__}: {len(results)} resultados")
        except Exception as e:
            print(f"[search_orchestrator] {search_fn.__name__} falhou: {e}")
            continue

    saved = save_search_results(search_id, query, all_results)
    print(f"[search_orchestrator] {saved}/{len(all_results)} resultados salvos | query='{query}' | id={search_id}")

    return search_id
```

---

## ✏️ PASSO 5 — Modificar `execution/worker_tasks.py`

Adicione a task abaixo **ao final do arquivo**, junto das tasks existentes (`process_price_check`, `schedule_all_products`). **Não modifique nenhuma task existente.**

```python
# ─────────────────────────────────────────────
# Task: Busca de produto por nome
# ─────────────────────────────────────────────

@celery_app.task(name="search_products")
def task_search_products(query: str) -> str:
    """
    Task Celery assíncrona que executa a busca de produtos por nome.
    Disparada pelo endpoint POST /search do web_server.py.

    Args:
        query: Nome do produto a buscar (ex: "Galaxy S24").

    Returns:
        search_id (UUID string) para consulta via GET /search/{search_id}.
    """
    from execution.search_orchestrator import run_product_search
    return run_product_search(query)
```

---

## ✏️ PASSO 6 — Modificar `execution/web_server.py`

Adicione as duas rotas abaixo **ao final do arquivo**, após os endpoints existentes (`/`, `/monitor/add`, `/product/{product_id}/history`). **Não modifique nenhuma rota existente.**

```python
# ─────────────────────────────────────────────
# Rotas: Busca automática de produtos por nome
# ─────────────────────────────────────────────

@app.post("/search")
def search_products(request: dict):
    """
    Recebe o nome do produto e dispara a busca assíncrona nas 3 lojas.
    Retorna imediatamente com o task_id — a busca roda em background no Celery.

    Body: {"query": "iPhone 15 128GB"}
    """
    query = request.get("query", "").strip()

    if not query:
        raise HTTPException(status_code=400, detail="Campo 'query' é obrigatório.")

    if len(query) < 2:
        raise HTTPException(status_code=400, detail="Query muito curta. Mínimo de 2 caracteres.")

    task = task_search_products.delay(query)

    return {
        "status":  "processing",
        "task_id": task.id,
        "query":   query,
        "message": "Busca iniciada. Use GET /search/{task_id} para consultar os resultados.",
    }


@app.get("/search/{search_id}")
def get_search_results(search_id: str):
    """
    Retorna os produtos encontrados para um search_id, ordenados por menor preço.

    Parâmetro: search_id retornado pelo POST /search (campo task_id).
    """
    from execution.db_client import get_search_results

    results = get_search_results(search_id)

    return {
        "search_id": search_id,
        "total":     len(results),
        "results":   results,
    }
```

> ⚠️ **Atenção:** O import de `task_search_products` no topo do `web_server.py` já deve existir se o arquivo já importa outras tasks. Caso contrário, adicione ao bloco de imports:
>
> ```python
> from execution.worker_tasks import task_search_products
> ```

---

## 🗂️ Estrutura final após a implementação

```
execution/
├── search_scrapers/               ✨ NOVA PASTA
│   ├── __init__.py                ✨ novo
│   ├── amazon_search.py           ✨ novo
│   ├── mercadolivre_search.py     ✨ novo
│   └── shopee_search.py           ✨ novo
├── search_orchestrator.py         ✨ novo
│
├── adapters/                      (sem alterações)
├── scrapers/                      (sem alterações)
├── scraping_orchestrator.py       (sem alterações)
├── cache_manager.py               (sem alterações)
├── firecrawl_api.py               (sem alterações)
├── store_detection.py             (sem alterações)
├── scheduler.py                   (sem alterações)
│
├── db_client.py                   ✏️ +2 funções ao final
├── worker_tasks.py                ✏️ +1 task ao final
└── web_server.py                  ✏️ +2 rotas ao final
```

---

## ✅ Checklist de Implementação

- [ ] Model `SearchResult` adicionado ao final do `schema.prisma`
- [ ] `prisma migrate dev --name add_search_results` executado com sucesso
- [ ] `prisma generate` executado com sucesso
- [ ] Funções `save_search_results` e `get_search_results` adicionadas ao `db_client.py`
- [ ] Pasta `execution/search_scrapers/` criada com os 4 arquivos
- [ ] `execution/search_orchestrator.py` criado
- [ ] Task `task_search_products` adicionada ao `worker_tasks.py`
- [ ] Import de `task_search_products` adicionado ao `web_server.py`
- [ ] Rotas `POST /search` e `GET /search/{search_id}` adicionadas ao `web_server.py`
- [ ] Containers reiniciados: `docker-compose up --build`

---

## ⚠️ Pontos de Atenção

- **Nenhuma nova dependência é necessária.** `httpx`, `beautifulsoup4` e `lxml` já estão no `requirements.txt` e instalados no Dockerfile.
- **Seletores CSS** da Amazon e Mercado Livre podem mudar se as lojas atualizarem o layout. Se um scraper retornar lista vazia, inspecione o HTML da página e atualize os seletores no arquivo correspondente — sem impactar o restante do sistema.
- **Shopee usa API JSON interna**, sendo a mais estável dos três. Se parar de funcionar, verifique se o endpoint mudou de versão (`v4` → outra).
- **O `search_id` retornado no `POST /search` é o `task.id` do Celery**, não um UUID gerado pelo orquestrador. O orquestrador gera seu próprio UUID internamente para agrupar os registros no banco. Para simplificar, considere alinhar os dois IDs se preferir usar apenas um identificador — mas isso é opcional para o MVP.
