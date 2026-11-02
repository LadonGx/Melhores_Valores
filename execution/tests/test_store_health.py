from execution import store_health


def _status(store):
    return next(s for s in store_health.get_stores_health() if s["store"] == store)


def test_sem_dados_fica_unknown():
    s = _status("amazon")
    assert s["status"] == "unknown"
    assert s["channels"]["search"]["status"] == "unknown"


def test_sucesso_fica_ok():
    store_health.record_ok("amazon", "search")
    store_health.record_ok("amazon", "monitor")
    assert _status("amazon")["status"] == "ok"


def test_busca_bloqueada_com_monitor_ok_fica_parcial():
    # Caso real do Mercado Livre: busca exige login, página do anúncio funciona
    store_health.record_ok("mercadolivre", "monitor")
    store_health.record_failure("mercadolivre", "search", "login_wall")
    s = _status("mercadolivre")
    assert s["status"] == "partial"
    assert s["channels"]["search"]["status"] == "blocked"
    assert s["channels"]["search"]["detail"] == "exigindo login"
    assert s["channels"]["monitor"]["status"] == "ok"


def test_sucesso_depois_da_falha_volta_a_ok(monkeypatch):
    times = iter(["2026-11-01T10:00:00+00:00", "2026-11-01T11:00:00+00:00"])
    monkeypatch.setattr(store_health, "_now_iso", lambda: next(times))
    store_health.record_failure("amazon", "search", "captcha")
    store_health.record_ok("amazon", "search")
    assert _status("amazon")["channels"]["search"]["status"] == "ok"


def test_falha_sem_categoria_e_erro_generico():
    store_health.record_failure("amazon", "monitor")
    ch = _status("amazon")["channels"]["monitor"]
    assert ch["status"] == "error"
    assert ch["category"] == "error"


def test_loja_ou_canal_desconhecido_e_ignorado(fake_store_health_redis):
    store_health.record_ok("shopee", "search")
    store_health.record_ok("amazon", "outro")
    assert fake_store_health_redis.data == {}


def test_redis_fora_do_ar_nao_quebra(monkeypatch):
    class Broken:
        def hset(self, *a, **k):
            raise ConnectionError("redis down")

        def hgetall(self, *a, **k):
            raise ConnectionError("redis down")

    monkeypatch.setattr(store_health, "redis_client", Broken())
    store_health.record_ok("amazon", "search")  # não levanta
    assert _status("amazon")["status"] == "unknown"
