"""
Testes do ponto de entrada do desktop: lock de instância única, escolha de
porta, detecção da instância já aberta e abertura do navegador.
"""

import io
import json
import logging
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, patch

import pytest

from execution import launcher


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "LOCK_PATH", tmp_path / "app.lock")
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(launcher, "PORT_PATH", tmp_path / "port")
    monkeypatch.setattr(launcher, "WEBVIEW_DIR", tmp_path / "webview")


def _serve(payload: dict | None):
    """Servidor HTTP real em 127.0.0.1 respondendo `payload` em /api/."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(payload).encode() if payload is not None else b"<html>"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


OUR_HEALTH = {"status": "ok", "message": "Price Tracker API is running"}


class TestIsOurApp:
    def test_recognizes_our_health_check(self):
        server = _serve(OUR_HEALTH)
        try:
            assert launcher.is_our_app(server.server_address[1]) is True
        finally:
            server.shutdown()

    @pytest.mark.parametrize("payload", [{"status": "ok", "message": "outro app"}, None])
    def test_other_programs_are_not_our_app(self, payload):
        server = _serve(payload)
        try:
            assert launcher.is_our_app(server.server_address[1]) is False
        finally:
            server.shutdown()

    def test_closed_port_is_not_our_app(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
        assert launcher.is_our_app(free_port, timeout=0.3) is False


class TestLock:
    def test_write_read_remove(self):
        launcher.write_lock(8123)
        assert launcher.read_lock() == {"pid": os.getpid(), "port": 8123}
        launcher.remove_lock()
        assert launcher.read_lock() is None

    def test_remove_keeps_lock_of_another_instance(self):
        launcher.LOCK_PATH.write_text(json.dumps({"pid": os.getpid() + 1, "port": 8123}))
        launcher.remove_lock()
        assert launcher.read_lock()["port"] == 8123

    @pytest.mark.parametrize("content", ["", "não é json", '{"port": "8000"}', "[]"])
    def test_corrupted_lock_is_ignored(self, content):
        launcher.LOCK_PATH.write_text(content, encoding="utf-8")
        assert launcher.read_lock() is None

    def test_running_instance_is_found_through_lock(self):
        launcher.write_lock(8123)
        with patch.object(launcher, "is_our_app", return_value=True) as check:
            assert launcher.find_running_instance() == 8123
        check.assert_called_once_with(8123)

    def test_stale_lock_is_ignored(self):
        launcher.write_lock(8123)
        with patch.object(launcher, "is_our_app", return_value=False):
            assert launcher.find_running_instance() is None

    def test_no_lock_means_no_instance(self):
        assert launcher.find_running_instance() is None


class TestStablePort:
    def test_default_when_nothing_saved(self):
        assert launcher.preferred_port(None) == launcher.DEFAULT_PORT

    def test_last_used_port_is_preferred(self):
        launcher.save_port(51234)
        assert launcher.saved_port() == 51234
        assert launcher.preferred_port(None) == 51234

    def test_cli_port_wins(self):
        launcher.save_port(51234)
        assert launcher.preferred_port(9000) == 9000

    @pytest.mark.parametrize("content", ["", "abc", "0", "70000"])
    def test_invalid_saved_port_is_ignored(self, content):
        launcher.PORT_PATH.write_text(content, encoding="utf-8")
        assert launcher.preferred_port(None) == launcher.DEFAULT_PORT

    def test_default_port_avoids_common_dev_ports_and_ephemeral_range(self):
        assert launcher.DEFAULT_PORT not in (3000, 5173, 8000, 8080)
        assert launcher.DEFAULT_PORT < 49152


class TestBindSocket:
    def test_uses_preferred_port_when_free(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
        sock = launcher.bind_socket(free_port)
        try:
            assert sock.getsockname() == ("127.0.0.1", free_port)
        finally:
            sock.close()

    def test_falls_back_to_free_port_when_preferred_is_busy(self):
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        busy_port = busy.getsockname()[1]
        try:
            sock = launcher.bind_socket(busy_port)
            try:
                host, port = sock.getsockname()
                assert host == "127.0.0.1"
                assert port not in (busy_port, 0)
            finally:
                sock.close()
        finally:
            busy.close()


class TestOpenBrowser:
    def test_opens_once_app_answers(self):
        answers = iter([False, False, True])
        with patch.object(launcher, "is_our_app", side_effect=lambda *a, **k: next(answers)), \
             patch.object(launcher.time, "sleep"), \
             patch.object(launcher.webbrowser, "open") as mock_open:
            assert launcher.open_browser_when_ready(8123) is True
        mock_open.assert_called_once_with("http://127.0.0.1:8123/")

    def test_gives_up_after_timeout(self):
        with patch.object(launcher, "is_our_app", return_value=False), \
             patch.object(launcher.webbrowser, "open") as mock_open:
            assert launcher.open_browser_when_ready(8123, timeout=0.3) is False
        mock_open.assert_not_called()


class TestMain:
    @pytest.fixture(autouse=True)
    def restore_logging(self):
        root = logging.getLogger()
        saved = root.handlers[:], root.level, logging.raiseExceptions
        yield
        for h in root.handlers:
            if h not in saved[0]:
                h.close()
        root.handlers, root.level, logging.raiseExceptions = saved

    def test_second_launch_brings_existing_window_to_front(self):
        with patch.object(launcher, "find_running_instance", return_value=8123), \
             patch.object(launcher, "focus_running_instance", return_value=True) as mock_focus, \
             patch.object(launcher.webbrowser, "open") as mock_open, \
             patch.object(launcher, "bind_socket") as mock_bind:
            assert launcher.main([]) == 0
        mock_focus.assert_called_once_with(8123)
        mock_open.assert_not_called()
        mock_bind.assert_not_called()

    def test_second_launch_opens_browser_when_instance_has_no_window(self):
        with patch.object(launcher, "find_running_instance", return_value=8123), \
             patch.object(launcher, "focus_running_instance", return_value=False), \
             patch.object(launcher.webbrowser, "open") as mock_open:
            assert launcher.main([]) == 0
        mock_open.assert_called_once_with("http://127.0.0.1:8123/")

    def test_second_launch_in_browser_mode_opens_browser(self):
        with patch.object(launcher, "find_running_instance", return_value=8123), \
             patch.object(launcher, "focus_running_instance") as mock_focus, \
             patch.object(launcher.webbrowser, "open") as mock_open:
            assert launcher.main(["--browser"]) == 0
        mock_focus.assert_not_called()
        mock_open.assert_called_once_with("http://127.0.0.1:8123/")

    def test_browser_and_no_browser_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            launcher.main(["--browser", "--no-browser"])

    def test_second_launch_with_no_browser(self):
        with patch.object(launcher, "find_running_instance", return_value=8123), \
             patch.object(launcher.webbrowser, "open") as mock_open:
            assert launcher.main(["--no-browser"]) == 0
        mock_open.assert_not_called()

    def test_log_with_char_missing_in_cp1252_never_breaks_the_caller(self, monkeypatch):
        """Regressão do .exe: "→" num stderr cp1252 abortava a migração do banco."""
        monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
        launcher.configure_logging()
        logging.getLogger("execution.db_client").info("Aplicando migração do banco: v0 → v1")  # não pode levantar
        assert "v0 → v1" in (launcher.LOG_DIR / "app.log").read_text(encoding="utf-8")

    def test_frozen_without_console_gets_utf8_streams(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", None)
        monkeypatch.setattr(sys, "stderr", None)
        with patch.object(launcher, "find_running_instance", return_value=8123):
            launcher.main(["--no-browser"])
        assert sys.stderr.encoding.lower().replace("-", "") == "utf8"
        print("v0 → v1", file=sys.stderr)  # não pode levantar
        sys.stdout.close()
        sys.stderr.close()

    def test_logging_goes_to_file(self):
        with patch.object(launcher, "find_running_instance", return_value=8123):
            launcher.main(["--no-browser"])
        log = (launcher.LOG_DIR / "app.log").read_text(encoding="utf-8")
        assert "já está aberto em http://127.0.0.1:8123/" in log


# ─── Janela nativa (pywebview) ────────────────────────────────────────────

class _FakeServer:
    """Imita o uvicorn.Server: run() "sobe" na hora e fica até should_exit."""

    def __init__(self, starts=True):
        self.started = False
        self.should_exit = False
        self._starts = starts
        self.ran_with = None

    def run(self, sockets=None):
        self.ran_with = sockets
        if self._starts:
            self.started = True
            while not self.should_exit:
                time.sleep(0.01)


def _fake_webview(start_side_effect=None):
    webview = MagicMock()
    webview.create_window.return_value = MagicMock(name="window")
    if start_side_effect:
        webview.start.side_effect = start_side_effect
    return webview


class TestRunWithWindow:
    def test_window_uses_persistent_storage_and_closing_stops_server(self, monkeypatch):
        from execution import desktop_app

        seen = {}

        def on_start(**kwargs):
            # durante a janela aberta, a 2ª abertura consegue trazê-la para frente
            seen["handler_registered"] = desktop_app._focus_handler is not None
            assert server.should_exit is False

        webview = _fake_webview(on_start)
        monkeypatch.setitem(sys.modules, "webview", webview)
        server = _FakeServer()

        launcher.run_with_window(server, sock=MagicMock(), port=8123)

        args, kwargs = webview.create_window.call_args
        assert args == ("Melhores Valores", "http://127.0.0.1:8123/")
        assert kwargs["text_select"] is True
        assert kwargs["background_color"] == "#0f1117"
        assert webview.start.call_args.kwargs == {"private_mode": False, "storage_path": str(launcher.WEBVIEW_DIR)}
        assert launcher.WEBVIEW_DIR.is_dir()
        assert seen["handler_registered"] is True
        assert desktop_app._focus_handler is None   # limpo ao fechar
        assert server.should_exit is True            # fechar a janela encerra o servidor

    def test_without_webview2_falls_back_to_browser(self, monkeypatch):
        webview = _fake_webview()
        webview.start.side_effect = RuntimeError("WebView2 runtime not found")
        monkeypatch.setitem(sys.modules, "webview", webview)
        server = _FakeServer()
        opened = []

        def open_and_stop(url):
            opened.append(url)
            server.should_exit = True  # simula o usuário encerrando depois

        with patch.object(launcher.webbrowser, "open", side_effect=open_and_stop):
            launcher.run_with_window(server, sock=MagicMock(), port=8123)

        assert opened == ["http://127.0.0.1:8123/"]

    def test_no_window_when_server_does_not_start(self, monkeypatch):
        webview = _fake_webview()
        monkeypatch.setitem(sys.modules, "webview", webview)
        monkeypatch.setattr(launcher, "STARTUP_TIMEOUT", 0.2)

        launcher.run_with_window(_FakeServer(starts=False), sock=MagicMock(), port=8123)

        webview.create_window.assert_not_called()

    def test_bring_to_front(self):
        window = MagicMock()
        launcher._bring_to_front(window)
        window.restore.assert_called_once()
        window.show.assert_called_once()
        assert window.on_top is False  # alternado True → False


class TestFocusRunningInstance:
    def test_true_when_instance_accepts(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

            def log_message(self, *args):
                pass

        received = []
        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            assert launcher.focus_running_instance(server.server_address[1]) is True
        finally:
            server.shutdown()
        assert received == ["/_desktop/focus"]

    def test_false_when_nothing_listens(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
        assert launcher.focus_running_instance(free_port) is False

class TestUnblockBundledFiles:
    """Regressão do v0.1.0 baixado do GitHub: arquivos extraídos do .zip vêm com a
    marca "veio da internet" e o .NET não carrega a Python.Runtime.dll do pywebview."""

    @pytest.mark.skipif(sys.platform != "win32", reason="fluxos NTFS (Zone.Identifier) só existem no Windows")
    def test_removes_internet_mark_from_every_file(self, tmp_path):
        files = [tmp_path / "Python.Runtime.dll", tmp_path / "sub" / "outro.pyd", tmp_path / "limpo.txt"]
        for f in files:
            f.parent.mkdir(exist_ok=True)
            f.write_bytes(b"conteudo")
        for f in files[:2]:
            with open(f"{f}:Zone.Identifier", "w") as stream:
                stream.write("[ZoneTransfer]\nZoneId=3\n")
        assert os.path.exists(f"{files[0]}:Zone.Identifier")

        assert launcher.unblock_bundled_files(tmp_path) == 2
        assert not any(os.path.exists(f"{f}:Zone.Identifier") for f in files)
        assert all(f.read_bytes() == b"conteudo" for f in files)  # conteúdo intacto
        assert launcher.unblock_bundled_files(tmp_path) == 0      # idempotente

    def test_noop_outside_windows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launcher.sys, "platform", "linux")
        (tmp_path / "a.dll").write_bytes(b"x")
        assert launcher.unblock_bundled_files(tmp_path) == 0

    @pytest.fixture
    def fake_start(self, monkeypatch):
        calls = {"unblock": [], "window": 0}
        monkeypatch.setattr(launcher, "find_running_instance", lambda: None)
        monkeypatch.setattr(launcher, "unblock_bundled_files", lambda root: calls["unblock"].append(root) or 0)
        monkeypatch.setattr(launcher, "run_with_window", lambda *a: calls.__setitem__("window", calls["window"] + 1))
        return calls

    def test_frozen_window_mode_unblocks_before_opening_the_window(self, fake_start, monkeypatch, tmp_path):
        monkeypatch.setattr(launcher, "is_frozen", lambda: True)
        monkeypatch.setattr(launcher.sys, "_MEIPASS", str(tmp_path), raising=False)
        assert launcher.main([]) == 0
        assert fake_start["unblock"] == [tmp_path] and fake_start["window"] == 1

    def test_running_from_source_does_not_touch_files(self, fake_start, monkeypatch):
        monkeypatch.setattr(launcher, "is_frozen", lambda: False)
        launcher.main([])
        assert fake_start["unblock"] == []