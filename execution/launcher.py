"""
Ponto de entrada do app desktop (chamado pelo main.py da raiz e pelo .exe).

- Janela própria (pywebview/WebView2): minimizar, restaurar, fechar = sair.
  `--browser` abre no navegador padrão; `--no-browser` só sobe o servidor.
- Instância única: se o app já está aberto, traz a janela dele para frente e sai.
- Porta estável: usa a mesma porta da última abertura (padrão 47290); só troca
  se ela estiver ocupada por outro programa. Estável porque o localStorage do
  frontend (grupos de produtos, filtros) é separado por porta.
- Escuta só em 127.0.0.1: nenhum outro computador da rede acessa o app.
- Logs vão para <pasta de dados>/logs/app.log (no .exe sem console não há terminal).
"""

import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler

from .settings import LOCK_PATH, LOG_DIR, PORT_PATH, WEBVIEW_DIR

HOST = "127.0.0.1"
# Fora das portas comuns de dev (8000, 3000, 5173...) e abaixo da faixa efêmera
# do Windows (49152+), para colidir o mínimo possível com outros programas
DEFAULT_PORT = 47290
# Texto do health check da API (GET /api/), usado para reconhecer uma instância nossa
_HEALTH_MARKER = "Price Tracker API"
STARTUP_TIMEOUT = 30.0

WINDOW_TITLE = "Melhores Valores"
WINDOW_BACKGROUND = "#0f1117"  # --color-bg do frontend (apps/web/src/styles/global.css)

logger = logging.getLogger("execution.launcher")


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(threadName)s] %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
    # Uma falha ao escrever log nunca pode derrubar quem chamou o log. No Python
    # 3.12, um UnicodeEncodeError dentro do handler escapa para o chamador (ex:
    # "migração v0 → v1" num stderr cp1252 abortava a migração do banco no .exe).
    logging.raiseExceptions = False
    # Uma linha por requisição do scraping polui o log sem ajudar no dia a dia
    logging.getLogger("httpx").setLevel(logging.WARNING)


def is_our_app(port: int, timeout: float = 1.0) -> bool:
    """True se há uma instância do Melhores Valores respondendo nessa porta."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/", timeout=timeout) as resp:
            body = json.loads(resp.read())
        return body.get("status") == "ok" and _HEALTH_MARKER in body.get("message", "")
    except (OSError, ValueError, AttributeError):
        return False


def read_lock() -> dict | None:
    try:
        data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("port"), int) else None
    except (OSError, ValueError):
        return None


def write_lock(port: int) -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps({"pid": os.getpid(), "port": port}), encoding="utf-8")


def remove_lock() -> None:
    """Apaga o lock só se for desta instância (outra pode ter assumido)."""
    lock = read_lock()
    if lock and lock.get("pid") == os.getpid():
        LOCK_PATH.unlink(missing_ok=True)


def saved_port() -> int | None:
    try:
        port = int(PORT_PATH.read_text(encoding="utf-8").strip())
        return port if 0 < port < 65536 else None
    except (OSError, ValueError):
        return None


def save_port(port: int) -> None:
    PORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PORT_PATH.write_text(str(port), encoding="utf-8")


def preferred_port(cli_port: int | None) -> int:
    """--port explícito > porta da última abertura > padrão."""
    return cli_port or saved_port() or DEFAULT_PORT


def find_running_instance() -> int | None:
    """Porta da instância já aberta, ou None. Lock antigo (app fechado à força) é ignorado."""
    lock = read_lock()
    if lock and is_our_app(lock["port"]):
        return lock["port"]
    return None


def _port_answers(port: int) -> bool:
    # No Windows, bind em 127.0.0.1 pode "funcionar" mesmo com outro programa
    # escutando em 0.0.0.0 na mesma porta; testar a conexão evita esse conflito.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex((HOST, port)) == 0


def bind_socket(preferred_port: int) -> socket.socket:
    """Socket já vinculado: na porta preferida se estiver livre, senão numa livre.
    Entregar o socket pronto ao uvicorn evita a corrida "testei livre → outro pegou"."""
    if preferred_port and not _port_answers(preferred_port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((HOST, preferred_port))
            return sock
        except OSError:
            sock.close()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, 0))
    logger.info("Porta %d ocupada — usando a porta %d", preferred_port, sock.getsockname()[1])
    return sock


def open_browser_when_ready(port: int, timeout: float = STARTUP_TIMEOUT) -> bool:
    url = f"http://{HOST}:{port}/"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_our_app(port, timeout=0.5):
            webbrowser.open(url)
            return True
        time.sleep(0.25)
    logger.error("O app não respondeu em %.0fs; abra %s manualmente", timeout, url)
    return False


def focus_running_instance(port: int) -> bool:
    """Pede à instância aberta para trazer a janela para frente. False se ela não tem janela."""
    request = urllib.request.Request(f"http://{HOST}:{port}/_desktop/focus", method="POST", data=b"")
    try:
        with urllib.request.urlopen(request, timeout=2) as resp:
            return resp.status == 200
    except OSError:
        return False


def _bring_to_front(window) -> None:
    window.restore()
    window.show()
    # No Windows, alternar "sempre no topo" é o jeito confiável de passar à frente
    window.on_top = True
    window.on_top = False


def _wait_until(condition, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def run_with_window(server, sock: socket.socket, port: int) -> None:
    """
    Servidor numa thread e a janela nativa (WebView2, via pywebview) na thread
    principal, como o pywebview exige. Fechar a janela encerra o servidor, e o
    lifespan desliga agendador e fila. Sem WebView2, cai para o navegador padrão.
    """
    from .desktop_app import set_focus_handler

    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, name="server", daemon=True)
    thread.start()
    if not _wait_until(lambda: server.started, STARTUP_TIMEOUT):
        logger.error("O servidor não subiu em %.0fs; encerrando", STARTUP_TIMEOUT)
        server.should_exit = True
        thread.join(timeout=10)
        return

    url = f"http://{HOST}:{port}/"
    try:
        import webview

        window = webview.create_window(
            WINDOW_TITLE, url,
            width=1280, height=820, min_size=(960, 640),
            background_color=WINDOW_BACKGROUND,  # mesma cor do app: sem "flash" branco ao abrir
            text_select=True,                    # permitir copiar nomes, preços, links
        )
        set_focus_handler(lambda: _bring_to_front(window))
        WEBVIEW_DIR.mkdir(parents=True, exist_ok=True)
        # private_mode=False + storage_path fixo: o padrão do pywebview é modo
        # privado, que apagaria o localStorage (grupos, filtros) a cada abertura
        webview.start(private_mode=False, storage_path=str(WEBVIEW_DIR))
        logger.info("Janela fechada — encerrando o app")
    except Exception:
        logger.exception("Não foi possível abrir a janela do app (WebView2?) — usando o navegador padrão")
        set_focus_handler(None)
        webbrowser.open(url)
        thread.join()  # segue rodando até o processo ser encerrado
        return
    finally:
        set_focus_handler(None)

    server.should_exit = True
    thread.join(timeout=15)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="MelhoresValores", description="Rastreador de preços (app local).")
    parser.add_argument(
        "--port", type=int, default=None,
        help=f"porta preferida (padrão: a da última abertura, ou {DEFAULT_PORT})",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--browser", action="store_true", help="abrir no navegador padrão em vez da janela do app")
    mode.add_argument("--no-browser", action="store_true", help="só o servidor, sem janela nem navegador")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # No .exe sem console, stdout/stderr são None e qualquer print derrubaria o app.
    # UTF-8 explícito: o padrão do Windows (cp1252) não codifica "→", acentos raros etc.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    # Console em cp1252: caractere sem equivalente vira \uXXXX em vez de erro
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    configure_logging()

    args = _parse_args(argv)
    mode = "browser" if args.browser else "none" if args.no_browser else "window"

    running_port = find_running_instance()
    if running_port:
        logger.info("O app já está aberto em http://%s:%d/", HOST, running_port)
        if mode == "window" and focus_running_instance(running_port):
            return 0
        if mode != "none":
            webbrowser.open(f"http://{HOST}:{running_port}/")
        return 0

    import uvicorn

    from .desktop_app import app

    sock = bind_socket(preferred_port(args.port))
    port = sock.getsockname()[1]
    write_lock(port)
    save_port(port)
    logger.info("Melhores Valores rodando em http://%s:%d/ (modo: %s)", HOST, port, mode)

    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
    try:
        if mode == "window":
            run_with_window(server, sock, port)
        else:
            if mode == "browser":
                threading.Thread(target=open_browser_when_ready, args=(port,), name="browser", daemon=True).start()
            server.run(sockets=[sock])
    finally:
        remove_lock()
        sock.close()
    return 0