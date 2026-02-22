from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from .adapters import normalize_store
from .worker_tasks import process_price_check

app = FastAPI(title="Rastreador de Preços - API")


class MonitorRequest(BaseModel):
    url: str
    store: Literal["amazon", "mercadolivre", "aliexpress"]


@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Price Tracker API is running"}


@app.post("/monitor/add")
async def add_product_to_monitor(payload: MonitorRequest):
    """Recebe uma nova URL para monitoramento e dispara a primeira verificação."""
    normalized_store = normalize_store(payload.store)
    task = process_price_check.delay(payload.url, normalized_store)
    return {
        "message": "URL enviada para a fila de processamento",
        "task_id": task.id,
        "status": "queued",
        "url": payload.url,
        "store": normalized_store,
    }
