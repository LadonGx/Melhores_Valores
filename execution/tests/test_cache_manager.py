"""
Testes do cache em memória (substituto do Redis no app desktop).
O relógio é injetado para testar expiração sem sleep.
"""

import threading
from unittest.mock import patch

import pytest

from execution import cache_manager
from execution.cache_manager import TTLCache


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def cache(clock):
    return TTLCache(clock=clock)


class TestTTLCache:
    def test_get_missing_key_returns_none(self, cache):
        assert cache.get("nada") is None

    def test_value_is_returned_before_ttl(self, cache, clock):
        cache.setex("k", 10, "v")
        clock.now += 9.9
        assert cache.get("k") == "v"

    def test_value_expires_at_ttl(self, cache, clock):
        cache.setex("k", 10, "v")
        clock.now += 10
        assert cache.get("k") is None

    def test_setex_overwrites_value_and_ttl(self, cache, clock):
        cache.setex("k", 10, "v1")
        clock.now += 8
        cache.setex("k", 10, "v2")
        clock.now += 8
        assert cache.get("k") == "v2"

    def test_expired_keys_are_pruned_when_cache_grows(self, cache, clock):
        for i in range(TTLCache._PRUNE_THRESHOLD):
            cache.setex(f"old-{i}", 1, "x")
        clock.now += 5
        cache.setex("new", 60, "y")  # passa do limite → varre as expiradas
        assert len(cache._data) == 1
        assert cache.get("new") == "y"

    def test_clear(self, cache):
        cache.setex("k", 10, "v")
        cache.clear()
        assert cache.get("k") is None

    def test_concurrent_access(self, cache):
        errors: list[Exception] = []

        def worker(n: int):
            try:
                for i in range(2000):
                    cache.setex(f"{n}-{i % 50}", 60, i)
                    cache.get(f"{(n + 1) % 4}-{i % 50}")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(cache._data) == 200


class TestPriceCache:
    @pytest.fixture(autouse=True)
    def isolated_cache(self, cache):
        with patch.object(cache_manager, "memory_cache", cache):
            yield

    def test_round_trip(self):
        cache_manager.set_cached_price("https://a", 99.9, name="Mouse", store="amazon")
        assert cache_manager.get_cached_price("https://a") == {
            "url": "https://a", "price": 99.9, "name": "Mouse", "store": "amazon",
        }

    def test_miss_returns_none(self):
        assert cache_manager.get_cached_price("https://nao-cacheado") is None

    def test_default_ttl_is_two_hours(self, clock):
        cache_manager.set_cached_price("https://a", 10.0)
        clock.now += 7199
        assert cache_manager.get_cached_price("https://a") is not None
        clock.now += 1
        assert cache_manager.get_cached_price("https://a") is None

    def test_key_is_sha256_of_url(self, cache):
        cache_manager.set_cached_price("https://a", 10.0)
        [key] = cache._data
        assert key.startswith("price_cache:") and len(key) == len("price_cache:") + 64

    def test_returned_dict_is_a_copy(self):
        cache_manager.set_cached_price("https://a", 10.0)
        cache_manager.get_cached_price("https://a")["price"] = 0
        assert cache_manager.get_cached_price("https://a")["price"] == 10.0

    def test_corrupted_payload_returns_none(self, cache):
        cache.setex(cache_manager._cache_key("https://a"), 60, "not-json")
        assert cache_manager.get_cached_price("https://a") is None
