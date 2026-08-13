import logging
import os
from typing import Any
from urllib.parse import urlparse, urlunparse

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

from .adapters import normalize_store, parse_product_data
from .cache_manager import get_cached_price, set_cached_price
from .db_client import (
    add_price_history,
    get_all_products,
    get_last_valid_price_for_url,
    get_or_create_product,
    is_garbage_name as _is_garbage_name,
)
from .scraping_orchestrator import scrape_product
from .search_orchestrator import run_product_search

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
    in_stock: bool = True,
    product_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": "ok",
        "source": source,
        "url": url,
        "store": store,
        "name": name,
        "price": float(price),
        "in_stock": in_stock,
    }
    if product_id:
        payload["product_id"] = product_id
    return payload


# Maximum ratio between new price and last known price before flagging as anomalous.
# A 3x jump (e.g. R$100 → R$300 or R$300 → R$100) is treated as suspicious.
_PRICE_JUMP_FACTOR = 3.0


def _passes_sanity_check(url: str, new_price: float) -> bool:
    """
    Returns False if the new price deviates suspiciously from the last known price.
    Always returns True for new products (no history yet).
    Non-blocking: DB errors default to True so the pipeline never stalls.
    """
    try:
        last = get_last_valid_price_for_url(url)
        if last is None or last <= 0:
            return True
        ratio = new_price / last
        if ratio > _PRICE_JUMP_FACTOR or ratio < (1.0 / _PRICE_JUMP_FACTOR):
            logger.warning(
                "Sanity check: preço %.2f diverge %.1fx do último válido %.2f | url=%s",
                new_price, ratio, last, url,
            )
            return False
    except Exception:
        logger.exception("Sanity check falhou com exceção; aceitando preço | url=%s", url)
    return True


def run_price_pipeline(
    url: str,
    store: str,
    fallback_name: str | None = None,
    fallback_image: str | None = None,
    skip_cache: bool = False,
) -> dict[str, Any]:
    """Pipeline principal com integração real (Redis, Firecrawl e PostgreSQL).

    Args:
        skip_cache: Se True, ignora o cache Redis e força um novo scraping.
                    Deve ser True em refreshes manuais para garantir dados frescos.
    """
    if not url or not isinstance(url, str):
        raise ValueError("'url' deve ser uma string não vazia.")

    # Strip URL fragments (e.g. #polycard_client=...&tracking_id=...) — they break scraping
    parsed = urlparse(url)
    if parsed.fragment:
        url = urlunparse(parsed._replace(fragment=""))
        logger.info("URL normalizada: fragment removido | url=%s", url)

    normalized_store = normalize_store(store)

    if not skip_cache:
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
        # Todos os níveis da cascata falharam por motivo técnico (timeout, bloqueio,
        # Firecrawl indisponível, etc.) — nenhum adapter confirmou indisponibilidade,
        # então não grava histórico (evita marcar o produto como "fora de estoque"
        # por uma falha passageira). Só garante que o produto exista no DB.
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
    in_stock = parsed_data.get("in_stock", True)

    if not isinstance(product_price, (int, float)) or product_price <= 0:
        product = get_or_create_product(url=url, name=product_name, store=normalized_store, image_url=product_image)
        if not in_stock:
            # Confirmado fora de estoque pelo adapter — registra no histórico
            logger.info(
                "Produto confirmado fora de estoque sem preço | url=%s store=%s", url, normalized_store
            )
            add_price_history(product_id=product.id, price=None, in_stock=False)
            return {
                "status": "out_of_stock",
                "url": url,
                "store": normalized_store,
                "reason": "Produto fora de estoque.",
            }
        logger.warning(
            "Preço inválido extraído (%.2f) para url=%s store=%s. Abortando salvamento.",
            product_price or 0,
            url,
            normalized_store,
        )
        return {
            "status": "error",
            "url": url,
            "store": normalized_store,
            "reason": f"Preço inválido extraído: {product_price}. Possível bloqueio anti-bot.",
        }

    confidence = parsed_data.get("confidence_score", 1.0)
    if not _passes_sanity_check(url, float(product_price)):
        # Price jump detected. Only block the save when confidence is also low;
        # if the extractor is confident, the jump may be genuine (flash sale, restock).
        if confidence < 0.75:
            logger.warning(
                "Preço bloqueado por sanity check + baixa confiança | "
                "price=%.2f confidence=%.2f | url=%s",
                product_price, confidence, url,
            )
            if product_name:
                get_or_create_product(url=url, name=product_name, store=normalized_store, image_url=product_image)
            return {
                "status": "error",
                "url": url,
                "store": normalized_store,
                "reason": f"Preço {product_price} diverge do histórico e confiança é baixa ({confidence:.2f}). Não salvo.",
            }
        logger.warning(
            "Sanity check falhou mas confidence alta (%.2f) — salvando mesmo assim | url=%s",
            confidence, url,
        )

    product = get_or_create_product(url=url, name=product_name, store=normalized_store, image_url=product_image)
    add_price_history(product_id=product.id, price=float(product_price), in_stock=in_stock)

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
        in_stock=in_stock,
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
        if getattr(product, "status", "active") == "paused":
            # Monitoramento pausado pelo usuário (ex: anúncio fora de estoque) — não reenfileira.
            continue

        # Passa nome e imagem atuais como fallback para que re-checagens não sobrescrevam com lixo
        process_price_check.delay(product.url, product.store, product.name, product.imageUrl)
        scheduled += 1

    return {
        "status": "ok",
        "scheduled_products": scheduled,
    }


app.conf.beat_schedule = {
    "schedule-all-products-every-6-hours": {
        "task": "execution.worker_tasks.schedule_all_products",
        "schedule": crontab(minute=0, hour="*/6"),
    }
}


# ─────────────────────────────────────────────
# Task: Busca de produto por nome
# ─────────────────────────────────────────────

@app.task(bind=True, name="search_products")
def task_search_products(
    self,
    query: str,
    min_price: float | None = None,
    max_price: float | None = None,
) -> str:
    """
    Task Celery assíncrona que executa a busca de produtos por nome.
    Usa o próprio task.id como search_id para que o frontend consiga
    consultar os resultados via GET /search/{task_id}.

    Args:
        query:     Nome do produto a buscar (ex: "Galaxy S24").
        min_price: Preço mínimo opcional (inclusive) para filtrar os resultados.
        max_price: Preço máximo opcional (inclusive) para filtrar os resultados.

    Returns:
        search_id = self.request.id (mesmo ID retornado pelo POST /search).
    """
    return run_product_search(
        query, min_price=min_price, max_price=max_price, search_id=self.request.id
    )

