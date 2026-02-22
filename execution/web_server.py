from fastapi import FastAPI
from pydantic import BaseModel

from .worker_tasks import process_price_check

app = FastAPI(title="Rastreador de Preços - API")


class MonitorRequest(BaseModel):
    url: str
    store: str


@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Price Tracker API is running"}


@app.post("/monitor/add")
async def add_product_to_monitor(payload: MonitorRequest):
    """Recebe uma nova URL para monitoramento e dispara a primeira verificação."""
    process_price_check.delay(payload.url, payload.store)
    return {"message": "URL enviada para a fila de processamento"}
