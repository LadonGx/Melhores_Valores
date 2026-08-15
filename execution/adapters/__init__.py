from __future__ import annotations

from typing import Any

from . import amazon, mercadolivre

SUPPORTED_STORES = ("amazon", "mercadolivre")


def normalize_store(store: str) -> str:
    normalized_store = store.strip().lower()
    if normalized_store not in SUPPORTED_STORES:
        supported = ", ".join(SUPPORTED_STORES)
        raise ValueError(f"Loja '{store}' não suportada. Use: {supported}.")
    return normalized_store


def _get_adapter_module(store: str):
    normalized_store = normalize_store(store)
    adapters = {
        "amazon": amazon,
        "mercadolivre": mercadolivre,
    }
    return adapters[normalized_store]


def parse_product_data(store: str, raw_data: dict[str, Any]) -> dict[str, Any]:
    """Extrai dados normalizados de um payload bruto do Firecrawl."""
    adapter_module = _get_adapter_module(store)
    name = adapter_module.extract_name(raw_data)
    price = adapter_module.extract_price(raw_data)
    extract_in_stock = getattr(adapter_module, "extract_in_stock", None)
    in_stock = extract_in_stock(raw_data) if extract_in_stock else True
    return {"name": name, "price": price, "in_stock": in_stock}
