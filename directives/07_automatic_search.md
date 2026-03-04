# 🤖 Prompt de Implementação: Feature de Busca Automática de Produtos

> **Para:** IA da IDE (Google Antigravity)
> **Projeto:** Price Tracker
> **Objetivo:** Implementar um mecanismo de busca automática de produtos por nome nas lojas Amazon, Mercado Livre e Shopee, salvando os resultados em uma nova tabela no banco de dados PostgreSQL.

---

## 📌 Contexto do Projeto

Este projeto é um **Price Tracker** com a seguinte stack:

- **API:** FastAPI
- **Banco de dados:** PostgreSQL via Prisma ORM (`prisma-client-python`)
- **Fila de tarefas:** Celery + Celery Beat
- **Cache/Broker:** Redis
- **Scraping atual:** httpx + BeautifulSoup + Playwright (em cascata), com Firecrawl como fallback
- **Padrão de projeto:** Adapters por loja, orquestrador central, workers assíncronos

O fluxo esperado da nova feature:

1. Usuário envia `POST /search` com o nome do produto
2. FastAPI despacha uma task Celery (assíncrono)
3. O worker busca o produto nas 3 lojas simultaneamente
4. Os resultados são normalizados e salvos no PostgreSQL
5. Usuário consulta `GET /search/{search_id}` para ver os resultados

---

## 🗄️ PASSO 1 — Atualizar o `schema.prisma`

Adicione o model abaixo ao arquivo `schema.prisma` existente:

```prisma
model SearchResult {
  id           String   @id @default(cuid())
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

Após adicionar, rode o comando de migração do Prisma:

```bash
prisma migrate dev --name add_search_results
prisma generate
```

---

## 📁 PASSO 2 — Criar a pasta `execution/search_scrapers/`

Crie a pasta e os seguintes arquivos dentro dela:

### `execution/search_scrapers/__init__.py`

```python
# search_scrapers package
```

---

### `execution/search_scrapers/amazon_search.py`

**Motivo:** Faz scraping da página de resultados da Amazon via httpx + BeautifulSoup. A Amazon renderiza os resultados de busca no HTML estático, dispensando Playwright neste caso.

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
    """Busca produtos na Amazon BR e retorna lista normalizada de resultados."""
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

**Motivo:** Faz scraping da página de listagem do Mercado Livre. A página de busca do ML renderiza os cards de produto no HTML, funcionando com httpx simples na maioria dos casos.

```python
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

def search_mercadolivre(query: str, max_results: int = 10) -> list[dict]:
    """Busca produtos no Mercado Livre BR e retorna lista normalizada de resultados."""
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

**Motivo:** A Shopee carrega seus produtos via API interna JSON (não via HTML), o que torna esse scraper mais estável e rápido que os demais — sem necessidade de Playwright ou parsing de HTML.

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
    Mais estável que scraping de HTML pois os dados já chegam estruturados.
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
                info         = item.get("item_basic", {})
                shop_id      = info.get("shopid")
                item_id      = info.get("itemid")
                name         = info.get("name", "")
                price_raw    = info.get("price")       # vem em centavos * 100000
                image_id     = info.get("image", "")
                rating_obj   = info.get("item_rating", {})

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

## 📁 PASSO 3 — Criar `execution/search_orchestrator.py`

**Motivo:** Centraliza a lógica de busca nas 3 lojas, normaliza os dados e persiste no banco. Mantém o padrão do projeto de ter um orquestrador separado dos scrapers.

```python
import uuid
from execution.search_scrapers.amazon_search       import search_amazon
from execution.search_scrapers.mercadolivre_search import search_mercadolivre
from execution.search_scrapers.shopee_search       import search_shopee
from execution.db_client import db  # cliente Prisma já existente no projeto

def run_product_search(query: str) -> str:
    """
    Executa a busca do produto nas 3 lojas e persiste os resultados no banco.
    Retorna o search_id para o cliente consultar via GET /search/{search_id}.
    """
    search_id = str(uuid.uuid4())

    all_results = []
    for search_fn in [search_amazon, search_mercadolivre, search_shopee]:
        try:
            results = search_fn(query, max_results=10)
            all_results.extend(results)
        except Exception as e:
            print(f"[search_orchestrator] Scraper falhou: {e}")
            continue

    for item in all_results:
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
        except Exception as e:
            print(f"[search_orchestrator] Erro ao salvar item: {e}")
            continue

    print(f"[search_orchestrator] {len(all_results)} resultados salvos | query='{query}' | search_id={search_id}")
    return search_id
```

---

## ✏️ PASSO 4 — Modificar `execution/worker_tasks.py`

Adicione a nova task Celery ao arquivo existente. **Não remova nada**, apenas acrescente:

```python
# --- NOVA TASK: busca de produtos por nome ---
@celery_app.task
def task_search_products(query: str) -> str:
    """Task assíncrona que executa a busca de produtos nas lojas."""
    from execution.search_orchestrator import run_product_search
    return run_product_search(query)
```

---

## ✏️ PASSO 5 — Modificar `execution/web_server.py`

Adicione as duas novas rotas ao arquivo FastAPI existente. **Não remova nada**, apenas acrescente:

```python
from execution.worker_tasks import task_search_products
from execution.db_client import db

# --- ROTA: disparar busca ---
@app.post("/search")
async def search_products(body: dict):
    """
    Recebe o nome do produto e dispara a busca assíncrona nas 3 lojas.
    Retorna imediatamente com o task_id para acompanhamento.
    """
    query = body.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Campo 'query' é obrigatório.")

    task = task_search_products.delay(query)
    return {
        "status":  "processing",
        "task_id": task.id,
        "query":   query,
        "message": "Busca iniciada. Consulte /search/{search_id} quando concluída."
    }

# --- ROTA: consultar resultados ---
@app.get("/search/{search_id}")
async def get_search_results(search_id: str):
    """Retorna todos os produtos encontrados para um determinado search_id."""
    results = db.searchresult.find_many(
        where={"search_id": search_id},
        order={"price": "asc"}  # ordena do mais barato ao mais caro
    )
    return {
        "search_id": search_id,
        "total":     len(results),
        "results":   results,
    }
```

---

## 📦 PASSO 6 — Verificar `requirements.txt`

Confirme que as seguintes dependências já estão no `requirements.txt`. Se não estiverem, adicione-as:

```
httpx==0.27.0
beautifulsoup4==4.12.3
lxml==5.2.2
```

> `playwright` já deve estar presente se o prompt anterior foi implementado.

---

## 🗂️ Estrutura final de pastas após a implementação

```
execution/
├── search_scrapers/               ✨ NOVA PASTA
│   ├── __init__.py                ✨ novo
│   ├── amazon_search.py           ✨ novo
│   ├── mercadolivre_search.py     ✨ novo
│   └── shopee_search.py           ✨ novo
├── search_orchestrator.py         ✨ novo
├── adapters/
│   ├── amazon.py
│   ├── mercadolivre.py
│   └── aliexpress.py
├── scrapers/
│   ├── base_scraper.py
│   └── playwright_scraper.py
├── scraping_orchestrator.py
├── cache_manager.py
├── db_client.py
├── firecrawl_api.py
├── scheduler.py
├── store_detection.py
├── web_server.py                  ✏️ modificado (2 novas rotas)
└── worker_tasks.py                ✏️ modificado (1 nova task)
```

---

## ✅ Checklist de Implementação

- [ ] Model `SearchResult` adicionado ao `schema.prisma`
- [ ] Migration do Prisma executada (`prisma migrate dev`)
- [ ] Pasta `execution/search_scrapers/` criada com os 4 arquivos
- [ ] Arquivo `execution/search_orchestrator.py` criado
- [ ] Task `task_search_products` adicionada ao `worker_tasks.py`
- [ ] Rotas `POST /search` e `GET /search/{search_id}` adicionadas ao `web_server.py`
- [ ] Dependências verificadas no `requirements.txt`

---

## ⚠️ Pontos de Atenção

- **Seletores CSS:** Os seletores do BeautifulSoup para Amazon e Mercado Livre podem mudar se as lojas redesenharem suas páginas. Se um scraper retornar lista vazia, o primeiro passo é inspecionar os seletores.
- **Shopee API:** A Shopee é a mais estável por usar JSON interno, mas o endpoint pode mudar de versão (`v4` → `v5`). Monitore erros do tipo `[shopee_search] Erro`.
- **Rate limiting:** Para volume baixo (uso pessoal), não é necessário adicionar delays entre requisições agora. Se no futuro o volume crescer, adicione `time.sleep(1)` entre chamadas no orquestrador.
