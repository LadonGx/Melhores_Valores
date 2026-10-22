"""
Testes de settings.py: o executável nunca pode carregar o .env do repositório
(que tem as chaves do desenvolvedor) e deve achar o frontend empacotado.
"""

import importlib
import sys
from pathlib import Path

import pytest

from execution import settings


@pytest.fixture
def reload_settings(monkeypatch):
    """Recarrega settings.py com sys.frozen/_MEIPASS controlados e restaura no fim."""

    def _reload(frozen: bool, meipass: Path | None = None):
        if frozen:
            monkeypatch.setattr(sys, "frozen", True, raising=False)
        else:
            monkeypatch.delattr(sys, "frozen", raising=False)
        if meipass is not None:
            monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
        else:
            monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.delenv("MV_WEB_DIST", raising=False)
        settings.load_dotenv.reset_mock()  # dotenv é um MagicMock no conftest
        return importlib.reload(settings)

    yield _reload
    monkeypatch.undo()
    importlib.reload(settings)


def test_dev_loads_user_config_and_repo_env(reload_settings):
    s = reload_settings(frozen=False)
    calls = s.load_dotenv.call_args_list
    assert calls[0].args == (s.DATA_DIR / "config.env",)
    assert len(calls) == 2 and calls[1].args == ()


def test_frozen_never_loads_repo_env(reload_settings, tmp_path):
    s = reload_settings(frozen=True, meipass=tmp_path)
    calls = s.load_dotenv.call_args_list
    assert [c.args for c in calls] == [(s.DATA_DIR / "config.env",)]


def test_frozen_serves_packaged_frontend(reload_settings, tmp_path):
    s = reload_settings(frozen=True, meipass=tmp_path)
    assert s.WEB_DIST_DIR == tmp_path / "web_dist"


def test_dev_serves_repo_build(reload_settings):
    s = reload_settings(frozen=False)
    assert s.WEB_DIST_DIR == Path(s.__file__).resolve().parent.parent / "apps" / "web" / "dist"
