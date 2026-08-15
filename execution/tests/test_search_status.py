"""
Unit tests for execution/search_status.py — the ephemeral Redis-backed store
used to surface per-store search blocks (e.g. Mercado Livre login_wall) to the
frontend without touching the SearchResult DB schema.
"""

import json
from unittest.mock import patch, MagicMock

from execution.search_status import set_search_warnings, get_search_warnings


class TestSetSearchWarnings:
    def test_persists_warnings_with_ttl(self):
        mock_redis = MagicMock()
        with patch("execution.search_status.redis_client", mock_redis):
            set_search_warnings("search-1", {"mercadolivre": "login_wall"})

        mock_redis.setex.assert_called_once()
        key, ttl, payload = mock_redis.setex.call_args[0]
        assert key == "search_warnings:search-1"
        assert ttl == 1800
        assert json.loads(payload) == {"mercadolivre": "login_wall"}

    def test_does_nothing_when_warnings_is_empty(self):
        mock_redis = MagicMock()
        with patch("execution.search_status.redis_client", mock_redis):
            set_search_warnings("search-1", {})

        mock_redis.setex.assert_not_called()


class TestGetSearchWarnings:
    def test_returns_stored_warnings(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"mercadolivre": "login_wall"})
        with patch("execution.search_status.redis_client", mock_redis):
            result = get_search_warnings("search-1")

        assert result == {"mercadolivre": "login_wall"}

    def test_returns_empty_dict_when_nothing_stored(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with patch("execution.search_status.redis_client", mock_redis):
            result = get_search_warnings("search-1")

        assert result == {}

    def test_returns_empty_dict_on_corrupted_payload(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"not-json"
        with patch("execution.search_status.redis_client", mock_redis):
            result = get_search_warnings("search-1")

        assert result == {}
