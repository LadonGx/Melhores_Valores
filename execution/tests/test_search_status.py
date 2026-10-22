"""
Unit tests for execution/search_status.py — the ephemeral in-memory store
used to surface per-store search blocks (e.g. Mercado Livre login_wall) to the
frontend without touching the SearchResult DB schema.
"""

import json
from unittest.mock import patch, MagicMock

from execution.cache_manager import TTLCache
from execution.search_status import set_search_warnings, get_search_warnings


class TestSetSearchWarnings:
    def test_persists_warnings_with_ttl(self):
        mock_cache = MagicMock()
        with patch("execution.search_status.memory_cache", mock_cache):
            set_search_warnings("search-1", {"mercadolivre": "login_wall"})

        mock_cache.setex.assert_called_once()
        key, ttl, payload = mock_cache.setex.call_args[0]
        assert key == "search_warnings:search-1"
        assert ttl == 1800
        assert json.loads(payload) == {"mercadolivre": "login_wall"}

    def test_does_nothing_when_warnings_is_empty(self):
        mock_cache = MagicMock()
        with patch("execution.search_status.memory_cache", mock_cache):
            set_search_warnings("search-1", {})

        mock_cache.setex.assert_not_called()


class TestGetSearchWarnings:
    def test_returns_stored_warnings(self):
        mock_cache = MagicMock()
        mock_cache.get.return_value = json.dumps({"mercadolivre": "login_wall"})
        with patch("execution.search_status.memory_cache", mock_cache):
            result = get_search_warnings("search-1")

        assert result == {"mercadolivre": "login_wall"}

    def test_returns_empty_dict_when_nothing_stored(self):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        with patch("execution.search_status.memory_cache", mock_cache):
            result = get_search_warnings("search-1")

        assert result == {}

    def test_returns_empty_dict_on_corrupted_payload(self):
        mock_cache = MagicMock()
        mock_cache.get.return_value = b"not-json"
        with patch("execution.search_status.memory_cache", mock_cache):
            result = get_search_warnings("search-1")

        assert result == {}


class TestRoundTrip:
    def test_warnings_round_trip_and_expire(self):
        now = [0.0]
        cache = TTLCache(clock=lambda: now[0])
        with patch("execution.search_status.memory_cache", cache):
            set_search_warnings("search-1", {"amazon": "captcha"})
            assert get_search_warnings("search-1") == {"amazon": "captcha"}
            assert get_search_warnings("search-2") == {}

            now[0] = 1800
            assert get_search_warnings("search-1") == {}