"""
Testes do ponto de entrada do desktop: lock de instância única, escolha de
porta, detecção da instância já aberta e abertura do navegador.
"""

import json
import logging
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import pytest

from execution import launcher


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "LOCK_PATH", tmp_path / "app.lock")
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(launcher, "PORT_PATH", tmp_path / "port")


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
        saved = root.handlers[:], root.level
        yield
        for h in root.handlers:
            if h not in saved[0]:
                h.close()
        root.handlers, root.level = saved

    def test_second_launch_reuses_running_instance(self):
        with patch.object(launcher, "find_running_instance", return_value=8123), \
             patch.object(launcher.webbrowser, "open") as mock_open, \
             patch.object(launcher, "bind_socket") as mock_bind:
            assert launcher.main([]) == 0
        mock_open.assert_called_once_with("http://127.0.0.1:8123/")
        mock_bind.assert_not_called()

    def test_second_launch_with_no_browser(self):
        with patch.object(launcher, "find_running_instance", return_value=8123), \
             patch.object(launcher.webbrowser, "open") as mock_open:
            assert launcher.main(["--no-browser"]) == 0
        mock_open.assert_not_called()

    def test_logging_goes_to_file(self):
        with patch.object(launcher, "find_running_instance", return_value=8123):
            launcher.main(["--no-browser"])
        log = (launcher.LOG_DIR / "app.log").read_text(encoding="utf-8")
        assert "já está aberto em http://127.0.0.1:8123/" in log
