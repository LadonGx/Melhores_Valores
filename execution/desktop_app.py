"""
App raiz do executável desktop: API e frontend na mesma porta.

    /api/*  → web_server.app (rotas atuais, sem mudança)
    /*      → frontend buildado (apps/web/dist), com fallback para index.html

A API fica em /api porque o React Router tem páginas com os mesmos caminhos
de rotas da API (/products, /search): servidas na raiz, um F5 em /products
devolveria JSON. O frontend já chama `/api` por padrão (services/api.ts).
"""

import logging
from pathlib import Path, PurePosixPath
from typing import Callable

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from . import web_server
from .settings import WEB_DIST_DIR

logger = logging.getLogger(__name__)

_MISSING_BUILD_HTML = """<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><title>Melhores Valores</title>
<body style="font-family: system-ui, sans-serif; max-width: 40rem; margin: 4rem auto; padding: 0 1rem">
<h1>Frontend não encontrado</h1>
<p>A API está rodando em <a href="/api/">/api/</a>, mas o frontend ainda não foi buildado.</p>
<p>Na raiz do repositório, rode <code>pnpm install</code> e <code>pnpm build</code> e recarregue a página.</p>
<p><small>Procurado em: {path}</small></p>
</body></html>"""


class SPAStaticFiles(StaticFiles):
    """StaticFiles que devolve o index.html para rotas do React Router
    (/products, /search...) em vez de 404, para o F5 funcionar."""

    async def get_response(self, path: str, scope: Scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            # Caminho com extensão (ex: /assets/x.js) que não existe é 404 de verdade
            if exc.status_code != 404 or PurePosixPath(path).suffix:
                raise
            response = await super().get_response("index.html", scope)

        if response.media_type == "text/html":
            # index.html sem cache: depois de atualizar o app, o navegador pega os
            # novos assets (que têm hash no nome e podem ficar em cache à vontade)
            response.headers["Cache-Control"] = "no-cache"
        return response


# Registrado pelo launcher quando há janela nativa: traz a janela para frente
_focus_handler: Callable[[], None] | None = None


def set_focus_handler(handler: Callable[[], None] | None) -> None:
    global _focus_handler
    _focus_handler = handler


def create_app(web_dist: Path = WEB_DIST_DIR) -> FastAPI:
    # Sub-apps montados não rodam o próprio lifespan: o raiz assume o do web_server
    root = FastAPI(title="Melhores Valores", lifespan=web_server.lifespan, docs_url=None, redoc_url=None)

    # Fora de /api: é controle do app desktop, não parte da API do produto.
    # Precisa vir antes do mount "/" do frontend, que captura todos os caminhos.
    @root.post("/_desktop/focus", include_in_schema=False)
    async def focus_window():
        """Uma 2ª abertura do app pede para a janela já aberta vir para frente."""
        if _focus_handler is None:
            raise HTTPException(status_code=404)
        _focus_handler()
        return {"status": "ok"}

    root.mount("/api", web_server.app)

    if (web_dist / "index.html").is_file():
        root.mount("/", SPAStaticFiles(directory=web_dist, html=True), name="web")
    else:
        logger.warning("Frontend buildado não encontrado em %s — servindo só a API", web_dist)
        page = _MISSING_BUILD_HTML.format(path=web_dist)

        @root.get("/{path:path}", include_in_schema=False)
        async def missing_build(path: str):
            return HTMLResponse(page, status_code=503)

    return root


app = create_app()
