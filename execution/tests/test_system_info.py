"""
Testes da tela "Sobre": verificação de versão nova (Releases do GitHub,
simulados) e diagnóstico.
"""

from unittest.mock import patch

import pytest

from execution import system_info


@pytest.fixture(autouse=True)
def clear_cache():
    system_info._cache.clear()
    yield
    system_info._cache.clear()


def _release(tag, draft=False, prerelease=False):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease,
            "html_url": f"https://github.com/x/releases/tag/{tag}", "published_at": "2026-10-20T10:00:00Z"}


class TestVersions:
    @pytest.mark.parametrize("tag, expected", [
        ("v0.1.0", (0, 1, 0)), ("1.10.2", (1, 10, 2)), ("v2.0", None), ("nightly", None), (None, None),
    ])
    def test_parse_version(self, tag, expected):
        assert system_info.parse_version(tag) == expected

    def test_latest_ignores_drafts_and_bad_tags_but_counts_prereleases(self):
        releases = [
            _release("v0.2.0"),
            _release("v0.10.0", prerelease=True),   # versão de teste: conta
            _release("v9.9.9", draft=True),          # rascunho: nunca
            _release("nightly"),
        ]
        assert system_info.latest_release(releases)["tag_name"] == "v0.10.0"  # 10 > 2 (numérico, não texto)

    def test_no_releases(self):
        assert system_info.latest_release([]) is None


class TestCheckForUpdate:
    def test_newer_release_is_reported(self, monkeypatch):
        monkeypatch.setattr(system_info, "__version__", "0.1.0")
        with patch.object(system_info, "_fetch_releases", return_value=[_release("v0.2.0", prerelease=True)]):
            result = system_info.check_for_update()
        assert result["update_available"] is True
        assert result["latest"] == "0.2.0" and result["current"] == "0.1.0"
        assert result["url"].endswith("/v0.2.0")
        assert result["error"] is None

    def test_same_or_older_version_is_not_an_update(self, monkeypatch):
        monkeypatch.setattr(system_info, "__version__", "0.2.0")
        with patch.object(system_info, "_fetch_releases", return_value=[_release("v0.2.0"), _release("v0.1.0")]):
            assert system_info.check_for_update()["update_available"] is False

    def test_network_error_never_raises(self):
        with patch.object(system_info, "_fetch_releases", side_effect=OSError("sem internet")):
            result = system_info.check_for_update()
        assert result["update_available"] is False
        assert result["error"] == "Não foi possível consultar o GitHub agora."
        assert result["url"] == system_info.RELEASES_PAGE

    def test_result_is_cached_and_force_bypasses_it(self):
        with patch.object(system_info, "_fetch_releases", return_value=[]) as fetch:
            system_info.check_for_update()
            system_info.check_for_update()
            assert fetch.call_count == 1  # 2ª consulta veio do cache (limite de 60/h do GitHub)
            system_info.check_for_update(force=True)
            assert fetch.call_count == 2


class TestDiagnostics:
    def test_system_info_fields(self):
        info = system_info.get_system_info()
        assert info["version"] == system_info.__version__
        assert info["log_file"].endswith("app.log")
        assert isinstance(info["firecrawl_configured"], bool)
        assert set(info) >= {"data_dir", "db_path", "browser", "last_full_check", "os", "python", "frozen"}

    def test_open_folder_only_known_targets(self):
        with pytest.raises(ValueError, match="desconhecida"):
            system_info.open_folder("../../Windows")

    def test_open_folder_opens_the_logs_dir(self, monkeypatch, tmp_path):
        monkeypatch.setitem(system_info.FOLDERS, "logs", lambda: tmp_path / "logs")
        opened = []
        monkeypatch.setattr(system_info.sys, "platform", "win32")
        monkeypatch.setattr(system_info.os, "startfile", lambda p: opened.append(p), raising=False)
        path = system_info.open_folder("logs")
        assert opened == [tmp_path / "logs"] and path == str(tmp_path / "logs")
        assert (tmp_path / "logs").is_dir()
