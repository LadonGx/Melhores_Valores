from fastapi import FastAPI, BackgroundTasks
from .worker_tasks import process_price_check

app = FastAPI(title="Rastreador de Preços - API")

@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Price Tracker API is running"}

@app.post("/monitor/add")
async def add_product_to_monitor(url: str, store: str):
    """Recebe uma nova URL para monitoramento e dispara a primeira verificação."""
    process_price_check.delay(url, store)
    return {"message": "URL enviada para a fila de processamento"}

