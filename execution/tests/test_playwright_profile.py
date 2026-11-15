"""
Testes do navegador do nível 2: user agent coerente e perfil persistente.

Nenhum navegador de verdade é aberto: `sync_playwright` é substituído por uma
cadeia de mocks no módulo do scraper.
"""

from unittest.mock import MagicMock, patch

import pytest

from execution.scrapers import playwright_scraper as scraper
from execution.scrapers.playwright_scraper import fetch_html_playwright

ML_HOME = "https://www.mercadolivre.com.br/"
ML_URL = "https://www.mercadolivre.com.br/p/MLB123"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Cache de versão limpo e perfis sempre dentro do tmp_path."""
    monkeypatch.setattr(scraper, "_browser_version_cache", None)
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.delenv("BROWSER_PROFILE_MAX_MB", raising=False)


def _fake_playwright(version="131.0.6778.33", persistent_error=None, on_persistent=None):
    page = MagicMock()
    page.content.return_value = "<html>ok</html>"
    page.wait_for_selector.side_effect = Exception("selector not found")
    page.wait_for_load_state.side_effect = Exception("timeout")

    context = MagicMock()
    context.new_page.return_value = page

    browser = MagicMock()
    browser.version = version
    browser.new_context.return_value = context

    chromium = MagicMock()
    chromium.launch.return_value = browser

    def launch_persistent(*args, **kwargs):
        if on_persistent:
            on_persistent(*args, **kwargs)
        if persistent_error:
            raise persistent_error
        return context

    chromium.launch_persistent_context.side_effect = launch_persistent

    p = MagicMock()
    p.chromium = chromium
    cm = MagicMock()
    cm.__enter__.return_value = p
    return cm, p, browser, context, page


def _goto_urls(page):
    return [call.args[0] for call in page.goto.call_args_list]


def _run(cm, **kwargs):
    with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=cm):
        return fetch_html_playwright(ML_URL, **kwargs)


class TestUserAgent:
    def test_user_agent_built_from_browser_version(self):
        ua = scraper._build_user_agent("131.0.6778.33")
        assert ua == (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
        assert "Headless" not in ua

    def test_unparseable_version_gives_no_override(self):
        assert scraper._build_user_agent("???") is None
        assert scraper._build_user_agent(MagicMock()) is None

    def test_disposable_context_receives_ua_locale_timezone_and_language(self):
        cm, p, browser, _context, _page = _fake_playwright(version="131.0.6778.33")

        assert _run(cm) == "<html>ok</html>"

        kwargs = browser.new_context.call_args.kwargs
        assert kwargs["user_agent"].endswith("Chrome/131.0.0.0 Safari/537.36")
        assert "X11; Linux x86_64" in kwargs["user_agent"]
        assert "Headless" not in kwargs["user_agent"]
        assert kwargs["locale"] == "pt-BR"
        assert kwargs["timezone_id"] == "America/Sao_Paulo"
        assert kwargs["extra_http_headers"]["Accept-Language"] == "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"

    def test_uses_new_headless_channel(self):
        cm, p, _browser, _context, _page = _fake_playwright()
        _run(cm)
        launch_kwargs = p.chromium.launch.call_args.kwargs
        assert launch_kwargs["headless"] is True
        assert launch_kwargs["channel"] == "chromium"

    def test_stealth_script_does_not_fake_webdriver_or_plugins(self):
        assert "webdriver" not in scraper._STEALTH_JS
        assert "plugins" not in scraper._STEALTH_JS
        assert "pt-BR" in scraper._STEALTH_JS


class TestContextKind:
    def test_no_profile_uses_launch_and_new_context(self):
        cm, p, browser, _context, _page = _fake_playwright()

        _run(cm)

        p.chromium.launch.assert_called_once()
        browser.new_context.assert_called_once()
        p.chromium.launch_persistent_context.assert_not_called()
        browser.close.assert_called_once()

    def test_profile_uses_persistent_context_in_profile_dir(self, tmp_path):
        cm, p, browser, context, _page = _fake_playwright(version="131.0.6778.33")

        assert _run(cm, profile="mercadolivre") == "<html>ok</html>"

        p.chromium.launch_persistent_context.assert_called_once()
        call = p.chromium.launch_persistent_context.call_args
        assert call.args[0] == str(tmp_path / "profiles" / "mercadolivre")
        assert (tmp_path / "profiles" / "mercadolivre").is_dir()
        assert call.kwargs["user_agent"].endswith("Chrome/131.0.0.0 Safari/537.36")
        assert call.kwargs["locale"] == "pt-BR"
        assert call.kwargs["timezone_id"] == "America/Sao_Paulo"
        assert call.kwargs["extra_http_headers"]["Accept-Language"].startswith("pt-BR,pt;q=0.9")
        assert call.kwargs["channel"] == "chromium"
        # o navegador descartável só serviu para descobrir a versão
        browser.new_context.assert_not_called()
        context.close.assert_called_once()
        context.add_init_script.assert_called_once()
        context.route.assert_called_once()

    def test_browser_version_is_discovered_once_per_process(self):
        cm, p, _browser, _context, _page = _fake_playwright()

        _run(cm, profile="mercadolivre")
        _run(cm, profile="mercadolivre")

        assert p.chromium.launch.call_count == 1
        assert p.chromium.launch_persistent_context.call_count == 2

    def test_default_profile_dir_is_inside_repo(self, monkeypatch):
        monkeypatch.delenv("BROWSER_PROFILE_DIR", raising=False)
        root = scraper._profile_root()
        assert root.name == ".browser-profile"
        assert (root.parent / "execution").is_dir()


class TestWarmup:
    def test_empty_profile_visits_home_before_listing(self):
        cm, _p, _browser, _context, page = _fake_playwright()

        _run(cm, profile="mercadolivre")

        assert _goto_urls(page) == [ML_HOME, ML_URL]

    def test_used_profile_goes_straight_to_listing(self, tmp_path):
        profile_dir = tmp_path / "profiles" / "mercadolivre"
        profile_dir.mkdir(parents=True)
        (profile_dir / "Local State").write_text("{}")
        cm, _p, _browser, _context, page = _fake_playwright()

        _run(cm, profile="mercadolivre")

        assert _goto_urls(page) == [ML_URL]

    def test_second_run_after_first_does_not_warm_up_again(self):
        # o Chromium de verdade grava arquivos no perfil; o mock grava um para simular
        def write_state(user_data_dir, **_kwargs):
            from pathlib import Path
            (Path(user_data_dir) / "Local State").write_text("{}")

        cm, _p, _browser, _context, page = _fake_playwright(on_persistent=write_state)

        _run(cm, profile="mercadolivre")
        _run(cm, profile="mercadolivre")

        assert _goto_urls(page) == [ML_HOME, ML_URL, ML_URL]

    def test_explicit_warmup_url_equal_to_home_is_not_visited_twice(self):
        cm, _p, _browser, _context, page = _fake_playwright()

        _run(cm, profile="mercadolivre", warmup_url=ML_HOME)

        assert _goto_urls(page) == [ML_HOME, ML_URL]


class TestProfileMaintenance:
    def test_stale_singleton_files_are_removed_before_launch(self, tmp_path):
        profile_dir = tmp_path / "profiles" / "mercadolivre"
        profile_dir.mkdir(parents=True)
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            (profile_dir / name).write_text("stale")
        (profile_dir / "Cookies").write_text("keep")
        seen = {}

        def check(user_data_dir, **_kwargs):
            from pathlib import Path
            seen["names"] = sorted(p.name for p in Path(user_data_dir).iterdir())

        cm, _p, _browser, _context, _page = _fake_playwright(on_persistent=check)

        _run(cm, profile="mercadolivre")

        assert seen["names"] == ["Cookies"]

    def test_oversized_profile_is_recreated_before_opening(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BROWSER_PROFILE_MAX_MB", "1")
        profile_dir = tmp_path / "profiles" / "mercadolivre"
        profile_dir.mkdir(parents=True)
        (profile_dir / "Cache").write_bytes(b"x" * (2 * 1024 * 1024))
        seen = {}

        def check(user_data_dir, **_kwargs):
            from pathlib import Path
            seen["names"] = [p.name for p in Path(user_data_dir).iterdir()]

        cm, _p, _browser, _context, page = _fake_playwright(on_persistent=check)

        _run(cm, profile="mercadolivre")

        assert seen["names"] == []
        # perfil recriado = visitante novo = aquecimento
        assert _goto_urls(page) == [ML_HOME, ML_URL]

    def test_profile_under_limit_is_kept(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BROWSER_PROFILE_MAX_MB", "5")
        profile_dir = tmp_path / "profiles" / "mercadolivre"
        profile_dir.mkdir(parents=True)
        (profile_dir / "Cache").write_bytes(b"x" * (1024 * 1024))

        cm, _p, _browser, _context, page = _fake_playwright()
        _run(cm, profile="mercadolivre")

        assert (profile_dir / "Cache").exists()
        assert _goto_urls(page) == [ML_URL]

    def test_max_mb_defaults_to_300_on_invalid_value(self, monkeypatch):
        assert scraper._profile_max_mb() == 300
        monkeypatch.setenv("BROWSER_PROFILE_MAX_MB", "abc")
        assert scraper._profile_max_mb() == 300
        monkeypatch.setenv("BROWSER_PROFILE_MAX_MB", "50")
        assert scraper._profile_max_mb() == 50

    def test_profile_open_failure_falls_back_to_disposable_context(self):
        cm, p, browser, _context, page = _fake_playwright(
            persistent_error=Exception("The profile appears to be in use by another Chromium process")
        )

        result = _run(cm, profile="mercadolivre")

        assert result == "<html>ok</html>"
        browser.new_context.assert_called_once()
        # contexto descartável é um visitante novo: faz o aquecimento
        assert _goto_urls(page) == [ML_HOME, ML_URL]

    def test_failure_after_opening_returns_none_and_closes_context(self):
        cm, _p, _browser, context, page = _fake_playwright()
        page.goto.side_effect = Exception("Timeout 30000ms exceeded")

        assert _run(cm, profile="mercadolivre") is None
        context.close.assert_called()
