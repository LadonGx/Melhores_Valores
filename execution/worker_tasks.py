from celery import Celery
import os
from dotenv import load_dotenv
from .cache_manager import get_cached_price, set_cached_price
from .firecrawl_api import scrape_product_data
from .db_client import db, connect_db, disconnect_db


load_dotenv()

# Configuração do Worker Celery
app = Celery('tasks', broker=os.getenv("REDIS_URL", "redis://localhost:6379/1"))

@app.task
def process_price_check(url: str, store: str):
    """
    Pipeline Principal:
    1. Verifica Cache (cache_manager)
    2. Se vazio, chama Firecrawl (firecrawl_api)
    3. Processa via Adapter (adapters/)
    4. Salva no Banco (db_client)
    5. Atualiza o Cache
    """
    # TODO: Implementar orquestração das chamadas
    pass

# Importa o agendamento para que o Celery Beat o reconheça
from . import scheduler

