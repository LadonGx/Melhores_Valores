from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .db_client import get_product_with_history, get_search_results
from .store_detection import detect_store_from_url
from .worker_tasks import process_price_check, task_search_products

app = FastAPI(title="Rastreador de Preços - API")



class MonitorRequest(BaseModel):
    url: str


@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Price Tracker API is running"}


@app.post("/monitor/add")
async def add_product_to_monitor(payload: MonitorRequest):
    """Recebe uma nova URL para monitoramento e dispara a primeira verificação."""
    try:
        detected_store = detect_store_from_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task = process_price_check.delay(payload.url, detected_store)
    return {
        "message": "URL enviada para a fila de processamento",
        "task_id": task.id,
        "status": "queued",
        "url": payload.url,
        "store": detected_store,
    }


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

    return {
        "product": {
            "id": product_data.get("id"),
            "url": product_data.get("url"),
            "name": product_data.get("name"),
            "store": product_data.get("store"),
            "image_url": product_data.get("imageUrl"),
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

class SearchRequest(BaseModel):
    query: str


@app.post("/search")
def search_products(request: SearchRequest):
    """
    Recebe o nome do produto e dispara a busca assíncrona nas 3 lojas.
    Retorna imediatamente com o task_id — a busca roda em background no Celery.

    Body: {"query": "iPhone 15 128GB"}
    """
    query = request.query.strip()

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
def get_search_results_endpoint(search_id: str):
    """
    Retorna os produtos encontrados para um search_id, ordenados por menor preço.

    Parâmetro: search_id retornado pelo POST /search (campo task_id).
    """
    results = get_search_results(search_id)

    return {
        "search_id": search_id,
        "total":     len(results),
        "results":   [r.model_dump() for r in results],
    }
