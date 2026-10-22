"""
Testes do app raiz do desktop: API em /api e SPA com fallback para index.html.

O conftest substitui o httpx por um mock, então o TestClient não funciona aqui;
as requisições são feitas chamando o app ASGI diretamente.
"""

import asyncio
import json

import pytest

from execution import desktop_app, web_server


def _get(app, path: str) -> tuple[int, dict[str, str], bytes]:
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
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
