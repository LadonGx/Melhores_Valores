"""
Testes do agendamento espaçado do Mercado Livre (worker_tasks.run_schedule_all_products).

Sem Celery, Redis nem rede: `process_price_check` é um mock e o banco devolve produtos de mentira.
"""

import random
from unittest.mock import MagicMock, patch

import pytest

from execution import worker_tasks
from execution.store_lock import DEFAULT_LOCK_TIMEOUT_S, lock_timeout_s
from execution.worker_tasks import (
    BROKER_VISIBILITY_TIMEOUT_S,
    DEFAULT_ML_SCHEDULE_MAX_INTERVAL_S,
    DEFAULT_ML_SCHEDULE_MAX_WINDOW_S,
    DEFAULT_ML_SCHEDULE_MIN_INTERVAL_S,
    BACKGROUND_LOCK_WAIT_S,
    get_ml_schedule_config,
    plan_ml_countdowns,
    run_schedule_all_products,
)

MIN_S, MAX_S, WINDOW_S = 60.0, 180.0, 2700.0
EPS = 1e-6


def _product(n, store="mercadolivre", status="active", url="auto"):
    p = MagicMock()
    p.id = f"p{n}"
    p.url = f"https://exemplo/{store}/{n}" if url == "auto" else url
    p.store = store
    p.name = f"Produto {n}"
    p.imageUrl = f"https://img/{n}.png"
    p.status = status
    return p


def _run(products, seed=1):
    """Roda a rodada com `products`; devolve (retorno, mock da task)."""
    random.seed(seed)
    task = MagicMock()
    with patch("execution.worker_tasks.get_all_products", return_value=products), \
         patch("execution.worker_tasks.process_price_check", task):
        result = run_schedule_all_products()
    return result, task


def _ml_calls(task):
    return task.apply_async.call_args_list


def _countdowns(task):
    return [c.kwargs["countdown"] for c in _ml_calls(task)]


@pytest.fixture(autouse=True)
def clean_schedule_env(monkeypatch):
    for name in (
        "ML_SCHEDULE_MIN_INTERVAL_S",
        "ML_SCHEDULE_MAX_INTERVAL_S",
        "ML_SCHEDULE_MAX_WINDOW_S",
        "ML_LOCK_TIMEOUT_S",
    ):
        monkeypatch.delenv(name, raising=False)


# ─── Countdowns do Mercado Livre ──────────────────────────────────────────────

class TestMlSpacing:
    def test_countdowns_strictly_increasing_with_gaps_inside_range(self):
        _, task = _run([_product(i) for i in range(9)])
        countdowns = _countdowns(task)
        assert len(countdowns) == 9
        gaps = [b - a for a, b in zip(countdowns, countdowns[1:])]
        assert all(g > 0 for g in gaps)
        assert all(MIN_S - EPS <= g <= MAX_S + EPS for g in gaps)

    def test_first_check_leaves_with_zero_countdown(self):
        _, task = _run([_product(i) for i in range(5)])
        assert _countdowns(task)[0] == 0

    def test_gaps_are_random_not_fixed(self):
        _, task = _run([_product(i) for i in range(9)])
        countdowns = _countdowns(task)
        gaps = {round(b - a, 3) for a, b in zip(countdowns, countdowns[1:])}
        assert len(gaps) > 1

    def test_ml_uses_apply_async_with_scheduled_trigger_and_fallbacks(self):
        products = [_product(i) for i in range(3)]
        _, task = _run(products)
        task.delay.assert_not_called()
        for call in _ml_calls(task):
            assert call.kwargs["kwargs"] == {"trigger": "scheduled"}
            url, store, name, image = call.kwargs["args"]
            assert store == "mercadolivre"
            assert url.startswith("https://exemplo/mercadolivre/")
            assert name.startswith("Produto ")
            assert image.endswith(".png")

    def test_order_is_shuffled_between_rounds(self):
        products = [_product(i) for i in range(9)]
        orders = set()
        for seed in range(6):
            _, task = _run(products, seed=seed)
            order = tuple(c.kwargs["args"][0] for c in _ml_calls(task))
            assert sorted(order) == sorted(p.url for p in products)  # ninguém some nem repete
            orders.add(order)
        assert len(orders) > 1

    def test_shuffle_is_called_on_each_round(self):
        with patch("execution.worker_tasks.random.shuffle") as shuffle:
            _run([_product(i) for i in range(4)])
            _run([_product(i) for i in range(4)])
        assert shuffle.call_count == 2

    def test_single_ml_product_goes_out_immediately(self):
        result, task = _run([_product(1)])
        assert _countdowns(task) == [0]
        assert result["ml_window_s"] == 0


# ─── Teto da janela ───────────────────────────────────────────────────────────

class TestWindowCap:
    def test_forty_products_never_pass_the_window(self):
        for seed in range(5):
            _, task = _run([_product(i) for i in range(40)], seed=seed)
            countdowns = _countdowns(task)
            assert len(countdowns) == 40
            assert countdowns[-1] <= WINDOW_S + EPS
            assert all(b > a for a, b in zip(countdowns, countdowns[1:]))  # continua crescente

    def test_compressed_gaps_stay_random(self):
        _, task = _run([_product(i) for i in range(40)])
        countdowns = _countdowns(task)
        gaps = {round(b - a, 3) for a, b in zip(countdowns, countdowns[1:])}
        assert len(gaps) > 1

    def test_no_compression_when_sum_fits(self):
        random.seed(3)
        countdowns = plan_ml_countdowns(10, MIN_S, MAX_S, WINDOW_S)
        gaps = [b - a for a, b in zip(countdowns, countdowns[1:])]
        assert all(MIN_S <= g <= MAX_S for g in gaps)

    def test_plan_with_zero_products_is_empty(self):
        assert plan_ml_countdowns(0, MIN_S, MAX_S, WINDOW_S) == []

    def test_window_plus_lock_timeout_fits_in_visibility_timeout(self):
        assert BROKER_VISIBILITY_TIMEOUT_S == 3600
        assert DEFAULT_ML_SCHEDULE_MAX_WINDOW_S + DEFAULT_LOCK_TIMEOUT_S < BROKER_VISIBILITY_TIMEOUT_S
        # E, com a espera máxima pela trava de uma checagem agendada, ainda sobra folga.
        assert (
            DEFAULT_ML_SCHEDULE_MAX_WINDOW_S + BACKGROUND_LOCK_WAIT_S + DEFAULT_LOCK_TIMEOUT_S
            < BROKER_VISIBILITY_TIMEOUT_S
        )

    def test_visibility_timeout_is_declared_on_the_app(self):
        assert worker_tasks.app.conf.broker_transport_options == {"visibility_timeout": 3600}


# ─── Amazon, pausados e retorno ───────────────────────────────────────────────

class TestOtherStoresAndResult:
    def test_amazon_keeps_immediate_delay_with_scheduled_trigger(self):
        _, task = _run([_product(1, "amazon"), _product(2, "amazon")])
        task.apply_async.assert_not_called()
        assert task.delay.call_count == 2
        for call in task.delay.call_args_list:
            assert call.kwargs == {"trigger": "scheduled"}
            assert call.args[1] == "amazon"
            assert len(call.args) == 4  # url, store, nome, imagem

    def test_paused_and_incomplete_products_are_skipped(self):
        products = [
            _product(1, "amazon"),
            _product(2, "amazon", status="paused"),
            _product(3, "mercadolivre", status="paused"),
            _product(4, "mercadolivre", url=None),
            _product(5, "mercadolivre"),
        ]
        result, task = _run(products)
        assert task.delay.call_count == 1
        assert task.apply_async.call_count == 1
        assert result["scheduled_products"] == 2

    def test_result_counts_each_store_and_ml_window(self):
        products = [_product(i, "amazon") for i in range(3)] + [_product(10 + i) for i in range(4)]
        result, task = _run(products)
        assert result["status"] == "ok"
        assert result["scheduled_products"] == 7
        assert result["by_store"] == {"amazon": 3, "mercadolivre": 4}
        assert result["ml_window_s"] == pytest.approx(_countdowns(task)[-1], abs=0.1)
        assert result["ml_window_s"] > 0

    def test_no_products_returns_zeros(self):
        result, task = _run([])
        assert result == {"status": "ok", "scheduled_products": 0, "by_store": {}, "ml_window_s": 0.0}
        task.delay.assert_not_called()
        task.apply_async.assert_not_called()


# ─── Variáveis de ambiente ────────────────────────────────────────────────────

DEFAULTS = (
    DEFAULT_ML_SCHEDULE_MIN_INTERVAL_S,
    DEFAULT_ML_SCHEDULE_MAX_INTERVAL_S,
    DEFAULT_ML_SCHEDULE_MAX_WINDOW_S,
)


class TestScheduleConfig:
    def test_defaults(self):
        assert get_ml_schedule_config() == (60.0, 180.0, 2700.0)

    def test_valid_override(self, monkeypatch):
        monkeypatch.setenv("ML_SCHEDULE_MIN_INTERVAL_S", "30")
        monkeypatch.setenv("ML_SCHEDULE_MAX_INTERVAL_S", "90")
        monkeypatch.setenv("ML_SCHEDULE_MAX_WINDOW_S", "1200")
        assert get_ml_schedule_config() == (30.0, 90.0, 1200.0)

    def test_equal_min_and_max_is_allowed(self, monkeypatch):
        monkeypatch.setenv("ML_SCHEDULE_MIN_INTERVAL_S", "100")
        monkeypatch.setenv("ML_SCHEDULE_MAX_INTERVAL_S", "100")
        assert get_ml_schedule_config() == (100.0, 100.0, 2700.0)

    @pytest.mark.parametrize(
        "env",
        [
            {"ML_SCHEDULE_MIN_INTERVAL_S": "200", "ML_SCHEDULE_MAX_INTERVAL_S": "100"},  # min > max
            {"ML_SCHEDULE_MIN_INTERVAL_S": "0"},
            {"ML_SCHEDULE_MIN_INTERVAL_S": "-5"},
            {"ML_SCHEDULE_MAX_INTERVAL_S": "-1"},
            {"ML_SCHEDULE_MAX_WINDOW_S": "0"},
            {"ML_SCHEDULE_MAX_WINDOW_S": "abc"},
            {"ML_SCHEDULE_MIN_INTERVAL_S": "um minuto"},
            {"ML_SCHEDULE_MAX_WINDOW_S": "3500"},  # + trava de 300 s estoura os 3600 s do broker
        ],
    )
    def test_invalid_values_fall_back_to_defaults(self, monkeypatch, env):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        assert get_ml_schedule_config() == DEFAULTS

    def test_blank_values_use_defaults(self, monkeypatch):
        monkeypatch.setenv("ML_SCHEDULE_MIN_INTERVAL_S", "  ")
        assert get_ml_schedule_config() == DEFAULTS

    def test_custom_config_is_used_by_the_schedule(self, monkeypatch):
        monkeypatch.setenv("ML_SCHEDULE_MIN_INTERVAL_S", "10")
        monkeypatch.setenv("ML_SCHEDULE_MAX_INTERVAL_S", "20")
        _, task = _run([_product(i) for i in range(6)])
        countdowns = _countdowns(task)
        gaps = [b - a for a, b in zip(countdowns, countdowns[1:])]
        assert all(10 - EPS <= g <= 20 + EPS for g in gaps)

    def test_lock_timeout_env(self, monkeypatch):
        assert lock_timeout_s() == 300.0
        monkeypatch.setenv("ML_LOCK_TIMEOUT_S", "120")
        assert lock_timeout_s() == 120.0
        monkeypatch.setenv("ML_LOCK_TIMEOUT_S", "-3")
        assert lock_timeout_s() == 300.0
        monkeypatch.setenv("ML_LOCK_TIMEOUT_S", "xyz")
        assert lock_timeout_s() == 300.0
