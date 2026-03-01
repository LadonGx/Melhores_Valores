from urllib.parse import urlparse

SUPPORTED_STORE_PATTERNS: dict[str, tuple[str, ...]] = {
    "amazon": ("amazon.",),
    "aliexpress": ("aliexpress.",),
    "mercadolivre": ("mercadolivre.",),
}


def detect_store_from_url(url: str) -> str:
    """Deduz a loja com base no domínio da URL."""
    hostname = (urlparse(url).hostname or "").lower()

    if not hostname:
        raise ValueError("URL inválida: domínio não identificado.")

    for store, patterns in SUPPORTED_STORE_PATTERNS.items():
        if any(pattern in hostname for pattern in patterns):
            return store

    raise ValueError("Loja não suportada para a URL informada.")
