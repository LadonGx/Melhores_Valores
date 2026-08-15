import asyncio
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .db_client import (
    add_price_history, delete_product, get_all_products, get_or_create_product,
    get_product_by_id, get_product_with_history, get_products_with_history,
    get_search_results, update_product_name, update_product_status,
)
from .search_status import get_search_warnings
from .store_detection import detect_store_from_url
from .worker_tasks import process_price_check, run_price_pipeline, task_search_products


def _normalize_url(url: str) -> str:
    """Remove fragmentos (#tracking_params) e espaços da URL antes de armazenar."""
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(fragment=""))

app = FastAPI(title="Rastreador de Preços - API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)



class MonitorRequest(BaseModel):
    url: str
    name: str | None = None
    image_url: str | None = None
    price: float | None = None
    in_stock: bool = True


class UpdateNameRequest(BaseModel):
    name: str


class UpdateStatusRequest(BaseModel):
    status: str


class SearchRequest(BaseModel):
    query: str
    min_price: float | None = None
    max_price: float | None = None


@app.get("/products")
async def list_products():
    """Retorna todos os produtos com o preço mais recente."""
    products = get_all_products()
    result = []
    for p in products:
        latest = p.history[0] if p.history else None
        result.append({
            "id": p.id,
            "url": p.url,
            "name": p.name,
            "store": p.store,
            "image_url": p.imageUrl,
            "current_price": latest.price if latest else None,
            "in_stock": latest.inStock if latest else None,
            "status": p.status,
            "last_checked": latest.scrapedAt.isoformat() if latest and latest.scrapedAt else None,
            "created_at": p.createdAt.isoformat() if p.createdAt else None,
            "updated_at": p.updatedAt.isoformat() if p.updatedAt else None,
        })
    return {"total": len(result), "products": result}


def _compute_promotions(products: list) -> list[dict]:
    """
    Retorna produtos cujo preço mais recente é menor que todo o histórico anterior.

    O "atual" é sempre p.history[0] (checagem mais recente, histórico vem ordenado
    scrapedAt desc) — produtos cuja checagem mais recente confirmou indisponibilidade
    (price=None, inStock=False) são descartados, para nunca anunciar como "promoção"
    um produto que está fora de estoque agora.
    """
    promotions = []
    for p in products:
        if not p.history:
            continue
        latest = p.history[0]
        if latest.price is None or not latest.inStock:
            continue  # sem preço válido agora, ou confirmado fora de estoque

        previous_prices = [h.price for h in p.history[1:] if h.price is not None]
        if not previous_prices:
            continue  # sem histórico anterior suficiente para comparar

        current_price = latest.price
        previous_lowest = min(previous_prices)
        if current_price < previous_lowest:
            promotions.append({
                "id": p.id,
                "url": p.url,
                "name": p.name,
                "store": p.store,
                "image_url": p.imageUrl,
                "current_price": current_price,
                "previous_lowest_price": previous_lowest,
                "savings": round(previous_lowest - current_price, 2),
                "in_stock": latest.inStock,
            })
    return promotions


@app.get("/products/promotions")
async def list_promotions():
    """Retorna produtos cujo preço atual é menor que todo o histórico anterior."""
    products = get_products_with_history()
    promotions = _compute_promotions(products)
    return {"total": len(promotions), "promotions": promotions}


@app.delete("/product/{product_id}")
async def remove_product(product_id: str):
    """Remove um produto e seu histórico de preços do monitoramento."""
    removed = delete_product(product_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return {"status": "ok", "deleted_id": product_id}


@app.post("/product/{product_id}/refresh")
async def refresh_product_price(product_id: str):
    """
    Força um novo scraping imediato para um produto específico.
    Ignora o cache Redis e aguarda o resultado de forma síncrona.
    Retorna o novo preço ou um erro descritivo.
    """
    product = get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")

    try:
        result = await asyncio.to_thread(
            run_price_pipeline,
            product.url,
            product.store,
            product.name,       # fallback_name = nome atual (não deixa perder)
            product.imageUrl,   # fallback_image
            True,               # skip_cache = True → força scraping fresco
        )
    except Exception as exc:
        return {
            "status": "error",
            "reason": "exception",
            "detail": f"Erro interno ao executar scraping: {exc}",
        }

    if result.get("status") == "ok":
        return {
            "status": "ok",
            "price": result.get("price"),
            "in_stock": result.get("in_stock", True),
            "name": result.get("name"),
            "source": result.get("source"),
        }

    if result.get("status") == "out_of_stock":
        return {
            "status": "out_of_stock",
            "in_stock": False,
            "detail": "Produto confirmado fora de estoque pelo site.",
        }

    # Interpreta o motivo do erro para retornar mensagem amigável
    reason = result.get("reason", "")
    if "cascata" in reason.lower() or "extrair" in reason.lower():
        detail = (
            "Não foi possível obter os dados do anúncio. "
            "O produto pode ter sido removido, ou o site está bloqueando a verificação no momento."
        )
        error_code = "unavailable"
    elif "inválido" in reason.lower() or "anti-bot" in reason.lower():
        detail = "O site bloqueou a verificação de preço. Tente novamente em alguns minutos."
        error_code = "blocked"
    else:
        detail = f"Falha ao atualizar preço: {reason}"
        error_code = "scraping_failed"

    return {
        "status": "error",
        "reason": error_code,
        "detail": detail,
    }


@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Price Tracker API is running"}


@app.post("/monitor/add")
async def add_product_to_monitor(payload: MonitorRequest):
    """Recebe uma nova URL para monitoramento e dispara a primeira verificação."""
    clean_url = _normalize_url(payload.url)

    try:
        detected_store = detect_store_from_url(clean_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Cria o produto imediatamente com os dados do SearchResult, antes do scraper rodar.
    # Assim, mesmo que o scraper falhe, o produto aparece com nome e preço corretos.
    if payload.name and len(payload.name.strip()) >= 3:
        product = get_or_create_product(
            url=clean_url,
            name=payload.name,
            store=detected_store,
            image_url=payload.image_url,
        )
        # Se um preço conhecido foi passado, salva já como primeira entrada do histórico
        if payload.price is not None and payload.price > 0:
            add_price_history(
                product_id=product.id,
                price=payload.price,
                in_stock=payload.in_stock,
            )

    task = process_price_check.delay(clean_url, detected_store, payload.name, payload.image_url)
    return {
        "message": "URL enviada para a fila de processamento",
        "task_id": task.id,
        "status": "queued",
        "url": clean_url,
        "store": detected_store,
    }


@app.patch("/product/{product_id}/name")
async def update_product_name_endpoint(product_id: str, payload: UpdateNameRequest):
    """Permite corrigir manualmente o nome de um produto."""
    name = payload.name.strip()
    if len(name) < 3:
        raise HTTPException(status_code=400, detail="Nome deve ter ao menos 3 caracteres.")
    updated = update_product_name(product_id, name)
    if not updated:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return {"status": "ok", "id": product_id, "name": name}


@app.patch("/product/{product_id}/status")
async def update_product_status_endpoint(product_id: str, payload: UpdateStatusRequest):
    """Pausa ou reativa o monitoramento de um produto (soft-delete). Não apaga histórico."""
    if payload.status not in ("active", "paused"):
        raise HTTPException(status_code=400, detail="Status deve ser 'active' ou 'paused'.")
    updated = update_product_status(product_id, payload.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return {"status": "ok", "id": product_id, "product_status": payload.status}


@app.get("/product/{product_id}/history")
async def get_product_history(product_id: str):
    product_data = get_product_with_history(product_id)
    if not product_data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    history = product_data.get("history", [])
    prices = [item.get("price") for item in history if isinstance(item.get("price"), (int, float))]

    current_price = prices[0] if prices else None
    lowest_price = min(prices) if prices else None
    average_price = round(sum(prices) / len(prices), 2) if prices else None

    latest_entry = history[0] if history else None

    return {
        "product": {
            "id": product_data.get("id"),
            "url": product_data.get("url"),
            "name": product_data.get("name"),
            "store": product_data.get("store"),
            "image_url": product_data.get("imageUrl"),
            "status": product_data.get("status"),
            "in_stock": latest_entry.get("inStock") if latest_entry else None,
            "created_at": product_data.get("createdAt"),
            "updated_at": product_data.get("updatedAt"),
        },
        "current_price": current_price,
        "lowest_price": lowest_price,
        "average_price": average_price,
        "history": history,
    }


# ─────────────────────────────────────────────
# Rotas: Busca automática de produtos por nome
# ─────────────────────────────────────────────

@app.post("/search")
def search_products(request: SearchRequest):
    """
    Recebe o nome do produto e dispara a busca assíncrona nas 3 lojas.
    Retorna imediatamente com o task_id — a busca roda em background no Celery.

    Body: {"query": "iPhone 15 128GB", "min_price": 20, "max_price": 500}
    """
    query = request.query.strip()

    if not query:
        raise HTTPException(status_code=400, detail="Campo 'query' é obrigatório.")

    if len(query) < 2:
        raise HTTPException(status_code=400, detail="Query muito curta. Mínimo de 2 caracteres.")

    min_price, max_price = request.min_price, request.max_price

    if min_price is not None and min_price < 0:
        raise HTTPException(status_code=400, detail="'min_price' não pode ser negativo.")

    if max_price is not None and max_price < 0:
        raise HTTPException(status_code=400, detail="'max_price' não pode ser negativo.")

    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=400, detail="'min_price' não pode ser maior que 'max_price'.")

    task = task_search_products.delay(query, min_price, max_price)

    return {
        "status":    "processing",
        "task_id":   task.id,
        "query":     query,
        "min_price": min_price,
        "max_price": max_price,
        "message":   "Busca iniciada. Use GET /search/{task_id} para consultar os resultados.",
    }


@app.get("/search/{search_id}")
def get_search_results_endpoint(search_id: str):
    """
    Retorna os produtos encontrados para um search_id, ordenados por menor preço.

    Parâmetro: search_id retornado pelo POST /search (campo task_id).
    """
    results = get_search_results(search_id)

    return {
        "search_id": search_id,
        "total":     len(results),
        # mode='json' garante que datetime (found_at) seja serializado como ISO string
        "results":   [r.model_dump(mode="json") for r in results],
        # Lojas que bloquearam essa busca (ex: {"mercadolivre": "login_wall"}) — {} se nenhuma
        "store_warnings": get_search_warnings(search_id),
    }
