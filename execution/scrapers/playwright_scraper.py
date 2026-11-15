import logging
import os
import re
import shutil
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

try:  # trava de arquivo só existe em Linux/macOS; no Windows seguimos sem ela
    import fcntl
except ImportError:  # pragma: no cover - depende do SO
    fcntl = None

logger = logging.getLogger(__name__)

# ─── Navegador ──────────────────────────────────────────────────────────────
# `channel="chromium"` = "novo headless" (o mesmo Chromium completo, sem janela).
# O padrão do Playwright (chromium-headless-shell) expõe "HeadlessChrome" no
# `sec-ch-ua` e não tem plugins; o novo headless se comporta como um Chrome de
# verdade. Ver execution/scrapers/README.md.
_BROWSER_CHANNEL = "chromium"
_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
]
_LOCALE = "pt-BR"
_TIMEZONE = "America/Sao_Paulo"
_ACCEPT_LANGUAGE = "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
_VIEWPORT = {"width": 1280, "height": 800}
_UA_TEMPLATE = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/{major}.0.0.0 Safari/537.36"
)

# Script executado antes de qualquer JS da página. O novo headless já expõe
# `navigator.webdriver === false` (como o Chrome comum) e plugins reais, então
# só alinhamos `navigator.languages` ao Accept-Language e garantimos `window.chrome`.
_STEALTH_JS = """
Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
if (!window.chrome) { window.chrome = { runtime: {} }; }
"""

# Versão do Chromium instalado, descoberta uma vez por processo (o contexto
# persistente precisa do user agent antes de ser criado).
_browser_version_cache: str | None = None

# ─── Perfil persistente ─────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PROFILE_MAX_MB = 300
_PROFILE_LOCK_WAIT_S = 20.0
# Páginas visitadas quando o perfil está vazio (visitante novo faz a home primeiro)
_PROFILE_WARMUP_URLS = {"mercadolivre": "https://www.mercadolivre.com.br/"}


def _profile_root() -> Path:
    """Diretório-pai dos perfis (lido a cada chamada, para os testes e o compose)."""
    configured = os.environ.get("BROWSER_PROFILE_DIR", "").strip()
    return Path(configured) if configured else _REPO_ROOT / ".browser-profile"


def _profile_max_mb() -> int:
    raw = os.environ.get("BROWSER_PROFILE_MAX_MB", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_PROFILE_MAX_MB
    return value if value > 0 else _DEFAULT_PROFILE_MAX_MB


def _build_user_agent(browser_version: object) -> str | None:
    """User agent de Chrome estável desktop Linux com a versão real do navegador."""
    match = re.match(r"(\d+)\.", str(browser_version))
    if not match:
        return None
    return _UA_TEMPLATE.format(major=match.group(1))


def _launch_options() -> dict:
    return {"headless": True, "channel": _BROWSER_CHANNEL, "args": list(_LAUNCH_ARGS)}


def _context_options(user_agent: str | None) -> dict:
    options = {
        "locale": _LOCALE,
        "timezone_id": _TIMEZONE,
        "java_script_enabled": True,
        "viewport": dict(_VIEWPORT),
        "extra_http_headers": {"Accept-Language": _ACCEPT_LANGUAGE},
    }
    if user_agent:
        options["user_agent"] = user_agent
    return options


def _discover_browser_version(p) -> str | None:
    """Versão do Chromium (cache por processo). Abre um navegador descartável uma vez."""
    global _browser_version_cache
    if _browser_version_cache is None:
        probe = p.chromium.launch(**_launch_options())
        try:
            _browser_version_cache = str(probe.version)
        finally:
            probe.close()
    return _browser_version_cache


def _dir_size_mb(path: Path) -> float:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total / (1024 * 1024)


def _is_empty_dir(path: Path) -> bool:
    return not path.exists() or not any(path.iterdir())


def _enforce_profile_size(profile_dir: Path) -> None:
    """Perfil acima de BROWSER_PROFILE_MAX_MB é apagado (vira um visitante novo)."""
    if not profile_dir.exists():
        return
    limit = _profile_max_mb()
    size = _dir_size_mb(profile_dir)
    if size > limit:
        logger.warning(
            "playwright_scraper | perfil acima do limite, recriando | dir=%s | size_mb=%.1f | max_mb=%d",
            profile_dir, size, limit,
        )
        shutil.rmtree(profile_dir, ignore_errors=True)


def _clear_singleton_files(profile_dir: Path) -> None:
    """Remove SingletonLock/Cookie/Socket deixados por um Chromium que morreu.

    Quem chama já está dentro da trava global (Redis) e da trava de arquivo, então
    nenhum outro processo está usando o perfil: o que sobrou é lixo, e o Chromium
    recusaria abrir (ou perguntaria por "outro computador") por causa dele.
    """
    if not profile_dir.exists():
        return
    for entry in profile_dir.glob("Singleton*"):
        try:
            entry.unlink()
        except OSError as e:
            logger.warning("playwright_scraper | não removeu %s | error=%s", entry, e)


def _acquire_file_lock(lock_path: Path):
    """Trava de arquivo local do perfil. Devolve o handle, ou None se não conseguiu.

    Sem `fcntl` (Windows) devolve um handle nulo (`False`): segue sem travar.
    """
    if fcntl is None:
        return False
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")
    deadline = time.monotonic() + _PROFILE_LOCK_WAIT_S
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError:
            if time.monotonic() >= deadline:
                handle.close()
                return None
            time.sleep(0.5)


def _release_file_lock(handle) -> None:
    if not handle or fcntl is None:
        return
    try:
        fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        pass
    handle.close()


def _open_persistent_context(p, profile: str):
    """Abre o contexto persistente do perfil. Devolve (context, fechar, perfil_novo).

    Levanta exceção se o perfil não puder ser aberto — quem chama cai para o
    contexto descartável.
    """
    root = _profile_root()
    profile_dir = root / profile
    lock_handle = _acquire_file_lock(root / f"{profile}.lock")
    if lock_handle is None:
        raise RuntimeError(f"perfil em uso por outro processo local: {profile_dir}")
    try:
        _enforce_profile_size(profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        fresh = _is_empty_dir(profile_dir)
        _clear_singleton_files(profile_dir)
        version = _discover_browser_version(p)
        context = p.chromium.launch_persistent_context(
            str(profile_dir),
            **_launch_options(),
            **_context_options(_build_user_agent(version)),
        )
    except BaseException:
        _release_file_lock(lock_handle)
        raise

    def close() -> None:
        try:
            context.close()
        finally:
            _release_file_lock(lock_handle)

    return context, close, fresh


def _open_disposable_context(p):
    """Navegador + contexto descartáveis (sem cookies de visitas anteriores)."""
    browser = p.chromium.launch(**_launch_options())
    global _browser_version_cache
    _browser_version_cache = str(browser.version)
    context = browser.new_context(**_context_options(_build_user_agent(browser.version)))
    return context, browser.close


def fetch_html_playwright(
    url: str,
    wait_ms: int = 3000,
    wait_for_selectors: tuple[str, ...] | None = None,
    warmup_url: str | None = None,
    *,
    profile: str | None = None,
) -> str | None:
    """
    Nível 2 da cascata: renderização completa com Playwright.
    Usa domcontentloaded (mais rápido e confiável que networkidle) e aguarda
    um tempo fixo para execução de JS assíncrono após o carregamento inicial.

    Usa o novo headless do Chromium com user agent montado da versão real do
    navegador (Linux, sem "HeadlessChrome"), pt-BR e fuso de São Paulo.

    Args:
        wait_for_selectors: seletores a aguardar após o load (substitui os
            seletores padrão de página de produto — útil para páginas de
            listagem/busca, que nunca têm esses seletores).
        warmup_url: se informado, é visitada antes de `url` no mesmo contexto/
            sessão, para estabelecer cookies como uma navegação orgânica faria.
        profile: nome de um perfil persistente (hoje só "mercadolivre"). O perfil
            guarda cookies de visitante em `BROWSER_PROFILE_DIR/<profile>`, de uma
            checagem para outra. Perfil vazio recebe um aquecimento (home da loja)
            antes do anúncio. Quem usa `profile` deve estar dentro da trava global
            da loja. Se o perfil não abrir, a checagem segue com contexto
            descartável. `None` = contexto descartável.
    """
    close = None
    try:
        with sync_playwright() as p:
            context = None
            warmups: list[tuple[str, int]] = []  # (url, espera em ms)
            if profile:
                try:
                    context, close, fresh = _open_persistent_context(p, profile)
                except Exception as e:
                    logger.warning(
                        "playwright_scraper | perfil não abriu, usando contexto descartável | profile=%s | error=%s",
                        profile, e,
                    )
                    fresh = True  # contexto descartável = visitante novo
                profile_warmup = _PROFILE_WARMUP_URLS.get(profile)
                if fresh and profile_warmup:
                    warmups.append((profile_warmup, 3000))
            if context is None:
                context, close = _open_disposable_context(p)
            if warmup_url and warmup_url not in [w[0] for w in warmups]:
                warmups.append((warmup_url, 1500))

            # Injeta o script de evasão antes de qualquer JS da página
            context.add_init_script(_STEALTH_JS)

            # Bloquear fontes, imagens e media para acelerar carregamento
            def block_unnecessary(route):
                if route.request.resource_type in ("image", "font", "media"):
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", block_unnecessary)
            page = context.new_page()
            for warmup, warmup_wait_ms in warmups:
                # Visita a home primeiro para estabelecer cookies/sessão antes do
                # request "suspeito" ir direto para a página alvo (reduz a chance
                # de acionar muralhas anti-bot em páginas de listagem/busca).
                try:
                    page.goto(warmup, timeout=15000, wait_until="domcontentloaded")
                    page.wait_for_timeout(warmup_wait_ms)
                except Exception:
                    pass
            # domcontentloaded: aguarda só o HTML/CSS, sem esperar requests assíncronos infinitos
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            # Aguarda JS renderizar o conteúdo no DOM (baseline)
            page.wait_for_timeout(wait_ms)
            # Garante que qualquer redirect JS já finalizou antes de extrair HTML
            try:
                page.wait_for_load_state("load", timeout=10000)
            except Exception:
                pass
            # Aguarda um elemento de preço aparecer no DOM (útil para páginas de catálogo
            # com preço renderizado por componentes assíncronos como ML /p/ e /up/).
            # Se não aparecer em 5s, extrai o que já estiver disponível.
            _PRICE_SELECTORS = (
                "meta[itemprop='price']",
                "span.priceToPay",
                "span.a-offscreen",
                ".ui-pdp-price__second-line",
                "[class*='currentPriceText']",
            )
            for sel in (wait_for_selectors or _PRICE_SELECTORS):
                try:
                    page.wait_for_selector(sel, timeout=5000)
                    break
                except Exception:
                    continue
            html = page.content()
            close()
            close = None
            return html
    except Exception as e:
        logger.warning("playwright_scraper | falhou | url=%s | error=%s", url, e)
        if close is not None:
            try:
                close()
            except Exception:
                pass
        return None
