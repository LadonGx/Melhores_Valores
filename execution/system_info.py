"""
Informações do app desktop para a tela "Sobre": versão, verificação de versão
nova nos Releases do GitHub e diagnóstico para o testador mandar quando algo
der errado (pasta de dados, log, navegador do nível 2, Firecrawl).
"""

import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
from typing import Any

import httpx

from . import __version__, firecrawl_api
from .db_client import get_last_full_check
from .scrapers.playwright_scraper import browser_in_use
from .settings import DATA_DIR, DB_PATH, LOG_DIR, is_frozen

logger = logging.getLogger(__name__)

GITHUB_REPO = "LadonGx/Melhores_Valores"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=20"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
# Sem login a API do GitHub permite 60 consultas/hora por IP: consulta no máximo a cada 6 h
UPDATE_CACHE_SECONDS = 6 * 3600

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


def parse_version(tag: str | None) -> tuple[int, int, int] | None:
    match = _VERSION_RE.match((tag or "").strip())
    return tuple(int(p) for p in match.groups()) if match else None  # type: ignore[return-value]


def latest_release(releases: list[dict]) -> dict | None:
    """Release publicado (não rascunho) com a maior versão vX.Y.Z. Pré-releases contam:
    as versões de teste são publicadas assim."""
    candidates = [r for r in releases if not r.get("draft") and parse_version(r.get("tag_name"))]
    return max(candidates, key=lambda r: parse_version(r["tag_name"]), default=None)


def _fetch_releases() -> list[dict]:
    response = httpx.get(
        RELEASES_API,
        timeout=5,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"MelhoresValores/{__version__}"},
    )
    response.raise_for_status()
    return response.json()


def check_for_update(force: bool = False) -> dict[str, Any]:
    """
    Compara a versão instalada com o último Release do GitHub. Falha de rede
    nunca vira erro para o usuário: devolve update_available=False com o motivo.
    """
    with _cache_lock:
        cached = _cache.get("result")
        if cached and not force and time.monotonic() - _cache["at"] < UPDATE_CACHE_SECONDS:
            return cached

    result: dict[str, Any] = {
        "current": __version__,
        "latest": None,
        "update_available": False,
        "url": RELEASES_PAGE,
        "published_at": None,
        "error": None,
    }
    try:
        release = latest_release(_fetch_releases())
        if release:
            result["latest"] = release["tag_name"].lstrip("v")
            result["url"] = release.get("html_url") or RELEASES_PAGE
            result["published_at"] = release.get("published_at")
            current = parse_version(__version__)
            result["update_available"] = bool(current and parse_version(release["tag_name"]) > current)
    except Exception as e:
        logger.info("Verificação de versão nova falhou: %s", e)
        result["error"] = "Não foi possível consultar o GitHub agora."

    with _cache_lock:
        _cache.update(result=result, at=time.monotonic())
    return result


def get_system_info() -> dict[str, Any]:
    last = get_last_full_check()
    return {
        "version": __version__,
        "frozen": is_frozen(),
        "data_dir": str(DATA_DIR),
        "db_path": str(DB_PATH),
        "log_file": str(LOG_DIR / "app.log"),
        # None até o nível 2 ser usado pela primeira vez nesta abertura
        "browser": browser_in_use(),
        "firecrawl_configured": bool(firecrawl_api.FIRECRAWL_API_KEY),
        "last_full_check": last.isoformat() if last else None,
        "os": platform.platform(),
        "python": platform.python_version(),
    }


FOLDERS = {"data": lambda: DATA_DIR, "logs": lambda: LOG_DIR}


def open_folder(target: str) -> str:
    """Abre a pasta de dados ou de logs no Explorador de Arquivos. Só esses dois destinos."""
    if target not in FOLDERS:
        raise ValueError(f"Pasta desconhecida: {target!r}")
    path = FOLDERS[target]()
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 — caminho fixo do próprio app
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
    return str(path)
