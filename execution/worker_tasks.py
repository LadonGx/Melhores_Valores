import logging
import os
import random
import time
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
    mark_product_checked,
    record_check_attempt,
    set_product_format,
)
from .scraping_orchestrator import scrape_product_with_meta
from .search_orchestrator import run_product_search
from .store_lock import StoreBusyError, lock_timeout_s

load_dotenv()

logger = logging.getLogger(__name__)

# Configuração do Worker Celery
app = Celery("tasks", broker=os.getenv("REDIS_URL", "redis://localhost:6379/1"))

# Tempo que o Redis espera por um ack antes de reentregar uma mensagem. 3600 s é o padrão do
# Celery/Kombu para Redis; está declarado aqui porque o agendamento espaçado do Mercado Livre
# depende dele: tarefas com `countdown` ficam reservadas (sem ack) até o horário, e passar deste
# prazo as faria ser reentregues e rodar em duplicata. Ver ML_SCHEDULE_MAX_WINDOW_S abaixo.
BROKER_VISIBILITY_TIMEOUT_S = 3600
app.conf.broker_transport_options = {"visibility_timeout": BROKER_VISIBILITY_TIMEOUT_S}

# ─── Agendamento espaçado do Mercado Livre ────────────────────────────────────
# Em 11/11 as 9 checagens do ML das 15:00 caíram 9/9 em login_wall: a rodada enfileirava tudo
# junto e, com `--concurrency=2`, as 9 páginas abriam em ~1 min. Agora cada anúncio do ML sai
# com um intervalo aleatório do anterior (ver `schedule_all_products`).
DEFAULT_ML_SCHEDULE_MIN_INTERVAL_S = 60.0
DEFAULT_ML_SCHEDULE_MAX_INTERVAL_S = 180.0
DEFAULT_ML_SCHEDULE_MAX_WINDOW_S = 2700.0

# Espera pela trava global do ML (segundos), por origem da checagem:
#  - manual (botão "Atualizar preço", a API fica esperando a resposta): ~60 s;
#  - agendada / recém-adicionada (roda no worker; pode esperar mais, ocupando 1 dos slots):
#    240 s — menos que o `ML_LOCK_TIMEOUT_S` (300 s), então em geral a trava libera antes.
#    Se esgotar, a task reagenda a si mesma (retry) em 60–180 s, no máximo 3 vezes.
MANUAL_LOCK_WAIT_S = 60.0
BACKGROUND_LOCK_WAIT_S = 240.0
BUSY_RETRY_MIN_S = 60.0
BUSY_RETRY_MAX_S = 180.0
BUSY_MAX_RETRIES = 3


def _env_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def get_ml_schedule_config() -> tuple[float, float, float]:
    """(intervalo mínimo, intervalo máximo, teto da janela) do agendamento do ML, em segundos.

    Lê as variáveis ML_SCHEDULE_MIN_INTERVAL_S / ML_SCHEDULE_MAX_INTERVAL_S /
    ML_SCHEDULE_MAX_WINDOW_S. Valores ausentes usam o padrão; valores inválidos (não numéricos,
    não positivos, mínimo > máximo, ou janela que somada à trava estoura o visibility_timeout)
    descartam a configuração toda e voltam aos três padrões, com aviso no log.
    """
    defaults = (
        DEFAULT_ML_SCHEDULE_MIN_INTERVAL_S,
        DEFAULT_ML_SCHEDULE_MAX_INTERVAL_S,
        DEFAULT_ML_SCHEDULE_MAX_WINDOW_S,
    )
    values = []
    for name, default in zip(
        ("ML_SCHEDULE_MIN_INTERVAL_S", "ML_SCHEDULE_MAX_INTERVAL_S", "ML_SCHEDULE_MAX_WINDOW_S"),
        defaults,
    ):
        value = _env_float(name)
        values.append(default if value is None else value)
    min_s, max_s, window_s = values

    if (
        min_s <= 0
        or max_s <= 0
        or window_s <= 0
        or min_s > max_s
        or window_s + lock_timeout_s() >= BROKER_VISIBILITY_TIMEOUT_S
    ):
        logger.warning(
            "Configuração de agendamento do ML inválida (min=%s max=%s janela=%s) — usando os padrões",
            min_s, max_s, window_s,
        )
        return defaults
    return min_s, max_s, window_s


def plan_ml_countdowns(count: int, min_s: float, max_s: float, window_s: float) -> list[float]:
    """Countdowns (segundos a partir de agora) para `count` checagens do ML.

    O primeiro sai com countdown 0 (a trava global está livre no começo da rodada); cada um dos
    seguintes espera um intervalo aleatório em [min_s, max_s] depois do anterior. Se a janela
    total passar de `window_s`, todos os intervalos são comprimidos pelo mesmo fator para caber
    — continuam aleatórios e a sequência continua estritamente crescente.
    """
    if count <= 0:
        return []
    gaps = [random.uniform(min_s, max_s) for _ in range(count - 1)]
    total = sum(gaps)
    if total > window_s:
        factor = window_s / total
        gaps = [gap * factor for gap in gaps]
    countdowns = [0.0]
    for gap in gaps:
        countdowns.append(countdowns[-1] + gap)
    return countdowns


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
    *,
    trigger: str = "added",
) -> dict[str, Any]:
    """Pipeline principal com integração real (Redis, Firecrawl e PostgreSQL).

    Args:
        skip_cache: Se True, ignora o cache Redis e força um novo scraping.
                    Deve ser True em refreshes manuais para garantir dados frescos.
        trigger: Origem da checagem — "scheduled" (Beat), "manual" (botão "Atualizar preço")
                 ou "added" (anúncio recém-cadastrado). Vai para o registro de tentativas e
                 define quanto tempo se espera pela trava do Mercado Livre.

    Raises:
        StoreBusyError: outra checagem do Mercado Livre segue em andamento e a espera esgotou.
            Nenhuma checagem real aconteceu, então nada é marcado nem registrado.
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

    try:
        return _check_product(url, normalized_store, fallback_name, fallback_image, trigger)
    except StoreBusyError:
        raise
    except Exception:
        _mark_unexpected_failure(url, normalized_store, fallback_name, fallback_image, trigger)
        raise


def _lock_wait_for(trigger: str) -> float:
    """Quanto esperar pela trava global do ML, conforme a origem da checagem."""
    return MANUAL_LOCK_WAIT_S if trigger == "manual" else BACKGROUND_LOCK_WAIT_S


def _register_check(
    product_id: str,
    store: str,
    status: str,
    detail: str | None = None,
    *,
    trigger: str,
    level: int | None,
    duration_ms: int | None,
) -> None:
    """Marca a última verificação do produto e registra a tentativa (medição) — sempre juntos.

    `detail` é a categoria do bloqueio (status "blocked") ou o motivo do erro (status "error").
    """
    if detail is None:
        mark_product_checked(product_id, status)
    else:
        mark_product_checked(product_id, status, detail)
    record_check_attempt(
        product_id,
        store,
        status,
        block_category=detail if status == "blocked" else None,
        error=detail if status == "error" else None,
        level=level,
        duration_ms=duration_ms,
        trigger=trigger,
    )


def _apply_format(product_id: str, parsed_data: dict[str, Any]) -> None:
    """Grava o formato do anúncio (Kindle/físico) quando o adapter informa; senão não mexe."""
    if "format" in parsed_data:
        set_product_format(product_id, parsed_data["format"])


def _mark_unexpected_failure(
    url: str, store: str, fallback_name: str | None, fallback_image: str | None, trigger: str
) -> None:
    """Marca a checagem como `error`/`exception` quando o pipeline estourou uma exceção.

    Best effort: se o próprio banco for a causa, só loga — a exceção original segue para o chamador.
    """
    try:
        product = get_or_create_product(url=url, name=fallback_name, store=store, image_url=fallback_image)
        # Nível e duração ficam em branco: a exceção pode ter vindo de qualquer ponto.
        _register_check(
            product.id, store, "error", "exception", trigger=trigger, level=None, duration_ms=None
        )
    except Exception:
        logger.exception("Não foi possível registrar a falha da checagem | url=%s", url)


def _check_product(
    url: str, store: str, fallback_name: str | None, fallback_image: str | None, trigger: str
) -> dict[str, Any]:
    """Scraping real (cascata) + gravação no banco + registro do resultado da checagem."""
    outcome = scrape_product_with_meta(url, store=store, lock_wait_s=_lock_wait_for(trigger))
    scrape_result, block_category, level = outcome.result, outcome.block_category, outcome.level
    scrape_ms = outcome.duration_ms or 0
    meta = {"trigger": trigger, "level": level}
    if not scrape_result:
        # Todos os níveis da cascata falharam por motivo técnico (timeout, bloqueio,
        # Firecrawl indisponível, etc.) — nenhum adapter confirmou indisponibilidade,
        # então não grava histórico (evita marcar o produto como "fora de estoque"
        # por uma falha passageira). Só garante que o produto exista no DB.
        product = get_or_create_product(url=url, name=fallback_name, store=store, image_url=fallback_image)
        if block_category:
            _register_check(product.id, store, "blocked", block_category, duration_ms=scrape_ms, **meta)
        else:
            _register_check(product.id, store, "error", "scrape_failed", duration_ms=scrape_ms, **meta)
        return {
            "status": "error",
            "url": url,
            "store": store,
            "reason": "Falha ao extrair dados através da cascata.",
        }

    # Compatibilidade com Firecrawl / Nível 1 & 2
    parse_started = time.monotonic()
    if "data" in scrape_result:
        parsed_data = parse_product_data(store, scrape_result)
        source = "firecrawl"
    else:
        parsed_data = scrape_result
        source = "cascata"
    # Duração da checagem = scraping (sem a espera pela trava) + parsing.
    check_ms = scrape_ms + int((time.monotonic() - parse_started) * 1000)

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
        product = get_or_create_product(url=url, name=product_name, store=store, image_url=product_image)
        if parsed_data.get("offer_type") == "none":
            # Página lida corretamente, mas o anúncio está sem oferta principal e sem
            # preço "a partir de": não é falha nem fora de estoque — não grava histórico.
            logger.info("Anúncio sem oferta principal | url=%s store=%s", url, store)
            _register_check(product.id, store, "no_offer", duration_ms=check_ms, **meta)
            _apply_format(product.id, parsed_data)
            return {
                "status": "no_offer",
                "url": url,
                "store": store,
                "reason": "Anúncio sem oferta principal.",
            }
        if not in_stock:
            # Confirmado fora de estoque pelo adapter — registra no histórico
            logger.info(
                "Produto confirmado fora de estoque sem preço | url=%s store=%s", url, store
            )
            add_price_history(product_id=product.id, price=None, in_stock=False)
            _register_check(product.id, store, "out_of_stock", duration_ms=check_ms, **meta)
            _apply_format(product.id, parsed_data)
            return {
                "status": "out_of_stock",
                "url": url,
                "store": store,
                "reason": "Produto fora de estoque.",
            }
        logger.warning(
            "Preço inválido extraído (%.2f) para url=%s store=%s. Abortando salvamento.",
            product_price or 0,
            url,
            store,
        )
        _register_check(product.id, store, "error", "invalid_price", duration_ms=check_ms, **meta)
        return {
            "status": "error",
            "url": url,
            "store": store,
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
            product = get_or_create_product(url=url, name=product_name, store=store, image_url=product_image)
            _register_check(product.id, store, "error", "price_rejected", duration_ms=check_ms, **meta)
            return {
                "status": "error",
                "url": url,
                "store": store,
                "reason": f"Preço {product_price} diverge do histórico e confiança é baixa ({confidence:.2f}). Não salvo.",
            }
        logger.warning(
            "Sanity check falhou mas confidence alta (%.2f) — salvando mesmo assim | url=%s",
            confidence, url,
        )

    product = get_or_create_product(url=url, name=product_name, store=store, image_url=product_image)
    # A deduplicação pode não gravar nada; a checagem aconteceu de qualquer forma.
    add_price_history(
        product_id=product.id,
        price=float(product_price),
        in_stock=in_stock,
        seller_type=parsed_data.get("seller_type"),
        seller_name=parsed_data.get("seller_name"),
    )
    _register_check(product.id, store, "ok", duration_ms=check_ms, **meta)
    _apply_format(product.id, parsed_data)

    set_cached_price(
        product_url=url,
        price=float(product_price),
        name=product_name,
        store=store,
        ttl=7200,
    )

    return _build_success_payload(
        source=source,
        url=url,
        store=store,
        name=product_name,
        price=float(product_price),
        in_stock=in_stock,
        product_id=product.id,
    )


def run_price_check_task(
    task: Any,
    url: str,
    store: str,
    fallback_name: str | None = None,
    fallback_image: str | None = None,
    trigger: str = "added",
) -> dict[str, Any]:
    """Corpo da task `process_price_check` (separado para testar sem Celery).

    Trava do ML ocupada (`StoreBusyError`): nenhuma checagem aconteceu, então nada é marcado nem
    registrado. A task se reagenda em 60–180 s (`task.retry`), até 3 vezes; esgotadas, devolve
    `{"status": "error", "reason": "busy"}` sem estourar exceção — a próxima rodada tenta de novo.
    """
    try:
        return run_price_pipeline(
            url=url,
            store=store,
            fallback_name=fallback_name,
            fallback_image=fallback_image,
            trigger=trigger,
        )
    except StoreBusyError as exc:
        retries = getattr(task.request, "retries", 0) or 0
        if retries < BUSY_MAX_RETRIES:
            countdown = random.uniform(BUSY_RETRY_MIN_S, BUSY_RETRY_MAX_S)
            logger.info(
                "Loja ocupada — reagendando em %.0fs (tentativa %d/%d) | url=%s",
                countdown, retries + 1, BUSY_MAX_RETRIES, url,
            )
            raise task.retry(exc=exc, countdown=countdown, max_retries=BUSY_MAX_RETRIES)
        logger.warning("Loja ocupada e retries esgotados — desistindo desta rodada | url=%s", url)
        return {"status": "error", "url": url, "store": store, "reason": "busy"}
    except Exception as exc:
        logger.exception("Erro no pipeline de preço. url=%s store=%s", url, store)
        return {
            "status": "error",
            "url": url,
            "store": store,
            "reason": str(exc),
        }


@app.task(bind=True)
def process_price_check(
    self,
    url: str,
    store: str,
    fallback_name: str | None = None,
    fallback_image: str | None = None,
    trigger: str = "added",
) -> dict[str, Any]:
    """Executa o pipeline de checagem com logs estruturados."""
    return run_price_check_task(self, url, store, fallback_name, fallback_image, trigger)


def run_schedule_all_products() -> dict[str, Any]:
    """Corpo da task `schedule_all_products` (separado para testar sem Celery).

    Amazon (e outras lojas): `.delay` imediato, como sempre.
    Mercado Livre: ordem embaralhada a cada rodada e cada checagem sai com um `countdown`
    acumulado — intervalo aleatório de ML_SCHEDULE_MIN/MAX_INTERVAL_S entre uma e outra, janela
    total limitada a ML_SCHEDULE_MAX_WINDOW_S (ver `plan_ml_countdowns`). O primeiro sai com
    countdown 0: a trava global está livre no início da rodada.
    """
    products = get_all_products()
    by_store: dict[str, int] = {}
    ml_items = []

    for product in products:
        if not product.url or not product.store:
            continue
        if getattr(product, "status", "active") == "paused":
            # Monitoramento pausado pelo usuário (ex: anúncio fora de estoque) — não reenfileira.
            continue

        by_store[product.store] = by_store.get(product.store, 0) + 1
        if product.store == "mercadolivre":
            ml_items.append(product)
            continue
        # Passa nome e imagem atuais como fallback para que re-checagens não sobrescrevam com lixo
        process_price_check.delay(
            product.url, product.store, product.name, product.imageUrl, trigger="scheduled"
        )

    ml_window_s = 0.0
    if ml_items:
        random.shuffle(ml_items)
        min_s, max_s, window_s = get_ml_schedule_config()
        countdowns = plan_ml_countdowns(len(ml_items), min_s, max_s, window_s)
        for product, countdown in zip(ml_items, countdowns):
            process_price_check.apply_async(
                args=(product.url, product.store, product.name, product.imageUrl),
                kwargs={"trigger": "scheduled"},
                countdown=countdown,
            )
        ml_window_s = round(countdowns[-1], 1)

    return {
        "status": "ok",
        "scheduled_products": sum(by_store.values()),
        "by_store": by_store,
        "ml_window_s": ml_window_s,
    }


@app.task
def schedule_all_products() -> dict[str, Any]:
    """Reenfileira todos os produtos cadastrados para nova checagem."""
    return run_schedule_all_products()


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

