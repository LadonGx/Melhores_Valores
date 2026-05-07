import logging
import os
from typing import Any

from celery import Celery
from dotenv import load_dotenv

from .adapters import normalize_store, parse_product_data
from .cache_manager import get_cached_price, set_cached_price
from .db_client import add_price_history, get_all_products, get_or_create_product
from .scraping_orchestrator import scrape_product

load_dotenv()

logger = logging.getLogger(__name__)

# Configuração do Worker Celery
app = Celery("tasks", broker=os.getenv("REDIS_URL", "redis://localhost:6379/1"))


def _build_success_payload(
    *,
    source: str,
    url: str,
    store: str,
    price: float,
    name: str | None,
    product_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": "ok",
        "source": source,
        "url": url,
        "store": store,
        "name": name,
        "price": float(price),
    }
    if product_id:
        payload["product_id"] = product_id
    return payload


# Fragmentos que indicam erro de scraping (substrings — inglês + português)
_GARBAGE_NAME_FRAGMENTS = {
    # Inglês
    "rate limited", "access denied", "forbidden", "captcha",
    "just a moment", "blocked", "unavailable", "cloudflare",
    # Português
    "acesso negado", "acesso bloqueado", "atenção", "você foi bloqueado",
    "não é possível", "página não encontrada", "verificação de segurança",
    "robô", "bot detectado",
}


def _is_garbage_name(name: str | None) -> bool:
    if not name or len(name.strip()) < 3:
        return True
    lower = name.strip().lower()
    return any(g in lower for g in _GARBAGE_NAME_FRAGMENTS)


def run_price_pipeline(
    url: str,
    store: str,
    fallback_name: str | None = None,
    fallback_image: str | None = None,
) -> dict[str, Any]:
    """Pipeline principal com integração real (Redis, Firecrawl e PostgreSQL)."""
    if not url or not isinstance(url, str):
        raise ValueError("'url' deve ser uma string não vazia.")

    normalized_store = normalize_store(store)

    cached_payload = get_cached_price(url)
    cached_price = cached_payload.get("price") if cached_payload else None
    if cached_payload and isinstance(cached_price, (int, float)) and cached_price > 0:
        # Aproveita o hit de cache mas garante nome correto no DB
        cached_name = cached_payload.get("name")
        best_name = cached_name if not _is_garbage_name(cached_name) else fallback_name
        get_or_create_product(url=url, name=best_name, store=normalized_store, image_url=fallback_image)
        return _build_success_payload(
            source="cache",
            url=url,
            store=normalized_store,
            price=float(cached_price),
            name=best_name,
        )

    scrape_result = scrape_product(url, store=normalized_store)
    if not scrape_result:
        # Sem scrape: ainda garante produto no DB com nome de fallback
        if fallback_name:
            get_or_create_product(url=url, name=fallback_name, store=normalized_store, image_url=fallback_image)
        return {
            "status": "error",
            "url": url,
            "store": normalized_store,
            "reason": "Falha ao extrair dados através da cascata.",
        }

    # Compatibilidade com Firecrawl / Nível 1 & 2
    if "data" in scrape_result:
        parsed_data = parse_product_data(normalized_store, scrape_result)
        source = "firecrawl"
    else:
        parsed_data = scrape_result
        if "name" not in parsed_data and "title" in parsed_data:
            parsed_data["name"] = parsed_data["title"]
        source = "cascata"

    product_name = parsed_data.get("name")
    product_image = parsed_data.get("image_url")

    # Usa fallback quando o scraper retornou lixo (rate limit, erro, etc.)
    if _is_garbage_name(product_name):
        logger.warning("Nome de scraping inválido '%s' — usando fallback '%s'", product_name, fallback_name)
        product_name = fallback_name
    if not product_image:
        product_image = fallback_image

    product_price = parsed_data.get("price")

    if not isinstance(product_price, (int, float)) or product_price <= 0:
        logger.warning(
            "Preço inválido extraído (%.2f) para url=%s store=%s. Abortando salvamento.",
            product_price or 0,
            url,
            normalized_store,
        )
        # Mesmo sem preço, cria/corrige o produto no DB com nome correto
        if product_name:
            get_or_create_product(url=url, name=product_name, store=normalized_store, image_url=product_image)
        return {
            "status": "error",
            "url": url,
            "store": normalized_store,
            "reason": f"Preço inválido extraído: {product_price}. Possível bloqueio anti-bot.",
        }

    product = get_or_create_product(url=url, name=product_name, store=normalized_store, image_url=product_image)
    add_price_history(product_id=product.id, price=float(product_price))

    set_cached_price(
        product_url=url,
        price=float(product_price),
        name=product_name,
        store=normalized_store,
        ttl=7200,
    )

    return _build_success_payload(
        source=source,
        url=url,
        store=normalized_store,
        name=product_name,
        price=float(product_price),
        product_id=product.id,
    )


@app.task
def process_price_check(
    url: str,
    store: str,
    fallback_name: str | None = None,
    fallback_image: str | None = None,
) -> dict[str, Any]:
    """Executa o pipeline de checagem com logs estruturados."""
    try:
        return run_price_pipeline(url=url, store=store, fallback_name=fallback_name, fallback_image=fallback_image)
    except Exception as exc:
        logger.exception("Erro no pipeline de preço. url=%s store=%s", url, store)
        return {
            "status": "error",
            "url": url,
            "store": store,
            "reason": str(exc),
        }


@app.task
def schedule_all_products() -> dict[str, Any]:
    """Reenfileira todos os produtos cadastrados para nova checagem."""
    products = get_all_products()
    scheduled = 0

    for product in products:
        if not product.url or not product.store:
            continue

        # Passa nome e imagem atuais como fallback para que re-checagens não sobrescrevam com lixo
        process_price_check.delay(product.url, product.store, product.name, product.imageUrl)
        scheduled += 1

    return {
        "status": "ok",
        "scheduled_products": scheduled,
    }


# Importa o agendamento para que o Celery Beat o reconheça
from . import scheduler


# ─────────────────────────────────────────────
# Task: Busca de produto por nome
# ─────────────────────────────────────────────

@app.task(bind=True, name="search_products")
def task_search_products(self, query: str) -> str:
    """
    Task Celery assíncrona que executa a busca de produtos por nome.
    Usa o próprio task.id como search_id para que o frontend consiga
    consultar os resultados via GET /search/{task_id}.

    Args:
        query: Nome do produto a buscar (ex: "Galaxy S24").

    Returns:
        search_id = self.request.id (mesmo ID retornado pelo POST /search).
    """
    from execution.search_orchestrator import run_product_search
    return run_product_search(query, search_id=self.request.id)

