"""
Testes do app raiz do desktop: API em /api e SPA com fallback para index.html.

O conftest substitui o httpx por um mock, então o TestClient não funciona aqui;
as requisições são feitas chamando o app ASGI diretamente.
"""

import asyncio
import json

import pytest

from execution import desktop_app, web_server


def _get(app, path: str, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 50000), "server": ("testserver", 80),
    }
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], headers, body


INDEX_HTML = b"<!doctype html><title>Melhores Valores</title><div id=root></div>"


@pytest.fixture
def web_dist(tmp_path):
    (tmp_path / "index.html").write_bytes(INDEX_HTML)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    return tmp_path


@pytest.fixture
def app(web_dist):
    return desktop_app.create_app(web_dist)


class TestSpa:
    def test_root_serves_index_without_cache(self, app):
        status, headers, body = _get(app, "/")
        assert status == 200
        assert body == INDEX_HTML
        assert headers["cache-control"] == "no-cache"

    @pytest.mark.parametrize("path", ["/products", "/search", "/products/", "/rota/qualquer"])
    def test_client_side_routes_fall_back_to_index(self, app, path):
        status, headers, body = _get(app, path)
        assert status == 200
        assert body == INDEX_HTML
        assert headers["content-type"].startswith("text/html")

    def test_assets_are_served(self, app):
        status, headers, body = _get(app, "/assets/index-abc123.js")
        assert status == 200
        assert body == b"console.log(1)"
        assert "cache-control" not in headers

    def test_missing_asset_is_a_real_404(self, app):
        status, _, _ = _get(app, "/assets/nao-existe.js")
        assert status == 404


class TestApiMount:
    def test_api_health_under_api_prefix(self, app):
        status, _, body = _get(app, "/api/")
        assert status == 200
        assert json.loads(body)["status"] == "ok"

    def test_api_route_is_json_not_spa(self, app):
        status, headers, body = _get(app, "/api/products")
        assert status == 200
        assert headers["content-type"] == "application/json"
        assert json.loads(body) == {"total": 0, "products": []}

    def test_unknown_api_route_is_404_json(self, app):
        status, headers, _ = _get(app, "/api/nao-existe")
        assert status == 404
        assert headers["content-type"] == "application/json"

    def test_root_reuses_web_server_lifespan(self, app):
        assert app.router.lifespan_context is web_server.lifespan


class TestMissingBuild:
    def test_pages_explain_how_to_build_and_api_still_works(self, tmp_path):
        app = desktop_app.create_app(tmp_path / "sem-build")

        status, _, body = _get(app, "/products")
        assert status == 503
        assert b"pnpm build" in body

        status, _, body = _get(app, "/api/")
        assert status == 200
        assert json.loads(body)["status"] == "ok"


class TestFocusEndpoint:
    @pytest.fixture(autouse=True)
    def no_handler(self):
        desktop_app.set_focus_handler(None)
        yield
        desktop_app.set_focus_handler(None)

    def test_404_when_running_without_window(self, app):
        status, _, _ = _get(app, "/_desktop/focus", method="POST")
        assert status == 404

    def test_calls_window_handler(self, app):
        calls = []
        desktop_app.set_focus_handler(lambda: calls.append(1))
        status, _, body = _get(app, "/_desktop/focus", method="POST")
        assert status == 200 and json.loads(body) == {"status": "ok"}
        assert calls == [1]

    def test_route_is_not_shadowed_by_the_spa(self, app):
        """O mount "/" do frontend captura tudo; a rota de foco precisa vir antes dele."""
        desktop_app.set_focus_handler(lambda: None)
        status, headers, _ = _get(app, "/_desktop/focus", method="POST")
        assert status == 200 and headers["content-type"] == "application/json"

class TestRefreshAllRoutes:
    def test_status_before_any_batch(self, app, monkeypatch):
        monkeypatch.setattr(web_server, "refresh_status", lambda: None)
        status, _, body = _get(app, "/api/products/refresh-all")
        assert status == 200
        assert json.loads(body) == {"running": False, "total": 0, "done": 0, "ok": 0, "failed": 0}

    def test_start_is_manual_and_skips_cache(self, app, monkeypatch):
        calls = []
        batch = {"id": "b1", "running": True, "trigger": "manual", "total": 3, "done": 0, "ok": 0, "failed": 0}

        def fake_schedule(**kwargs):
            calls.append(kwargs)
            return {"status": "ok", "scheduled_products": 3, "batch": batch}

        monkeypatch.setattr(web_server, "schedule_all_products", fake_schedule)
        status, _, body = _get(app, "/api/products/refresh-all", method="POST")
        assert status == 200
        assert json.loads(body) == {"started": True, **batch}
        assert calls == [{"skip_cache": True, "trigger": "manual"}]

    def test_start_while_running_reports_existing_batch(self, app, monkeypatch):
        batch = {"id": "b0", "running": True, "trigger": "agendada", "total": 20, "done": 7, "ok": 7, "failed": 0}
        monkeypatch.setattr(web_server, "schedule_all_products",
                            lambda **kw: {"status": "already_running", "scheduled_products": 0, "batch": batch})
        _, _, body = _get(app, "/api/products/refresh-all", method="POST")
        assert json.loads(body) == {"started": False, **batch}