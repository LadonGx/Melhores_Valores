# Diretiva 05: Caching Rules

Regras de como e quando usar o cache para evitar scraping duplicado (e chamadas pagas ao Firecrawl) no intervalo de X horas.

> Na branch `exe` o cache saiu do Redis e passou a viver em memória (`execution/cache_manager.py`, Fase 3 do `docs/plano-executavel.md`).

- **Onde:** `memory_cache` (classe `TTLCache`) em `cache_manager.py`. Expõe só `get(key)` e `setex(key, ttl, value)`, como era usado do Redis; é thread-safe.
- **Preço:** chave `price_cache:<sha256 da URL normalizada>`, valor JSON `{url, price, name, store}`, TTL de **2 horas** (`set_cached_price(..., ttl=7200)`). Não use outro TTL em outro lugar.
- **Avisos de busca:** `search_warnings:<search_id>`, TTL de 30 minutos (`search_status.py`).
- **Cache-first:** `run_price_pipeline` consulta o cache antes da cascata; só grava depois de um preço válido. Refresh manual passa `skip_cache=True`.
- **Vida útil:** o cache é do processo e some ao fechar o app. Isso é aceitável, porque ele é só otimização; o histórico de verdade fica no SQLite.
