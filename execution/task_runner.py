"""
Fila de tarefas em threads, no lugar do Celery worker.

Mantém a interface que o resto do código usava do Celery, para que
web_server.py e worker_tasks.py não precisem mudar:

    @task
    def process_price_check(url, store): ...

    handle = process_price_check.delay(url, store)   # roda em background
    handle.id                                        # uuid da tarefa

    @task(bind=True)
    def task_search_products(self, query): ...       # self.request.id == handle.id

Chamar a função direto (sem .delay) executa na thread atual, como no Celery.
"""

import functools
import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Igual ao --concurrency=2 do worker Celery: no máximo 2 scrapings simultâneos
MAX_WORKERS = 2

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="mv-task")
        return _executor


def shutdown(wait: bool = False) -> None:
    """Encerra o pool (no fechamento do app). Tarefas ainda na fila são descartadas."""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=wait, cancel_futures=True)
            _executor = None


@dataclass(frozen=True)
class TaskRequest:
    id: str


@dataclass(frozen=True)
class TaskContext:
    """O `self` recebido por tarefas com bind=True (como no Celery)."""
    request: TaskRequest


@dataclass(frozen=True)
class TaskHandle:
    """Retorno de .delay(): o id da tarefa e o Future com o resultado."""
    id: str
    future: Future


class Task:
    def __init__(self, fn: Callable[..., Any], bind: bool):
        self._fn = fn
        self._bind = bind
        functools.update_wrapper(self, fn)

    def _run(self, task_id: str, args: tuple, kwargs: dict) -> Any:
        if self._bind:
            return self._fn(TaskContext(TaskRequest(task_id)), *args, **kwargs)
        return self._fn(*args, **kwargs)

    def _run_logged(self, task_id: str, args: tuple, kwargs: dict) -> Any:
        try:
            return self._run(task_id, args, kwargs)
        except Exception:
            # Sem isso a exceção ficaria guardada no Future, que ninguém consulta
            logger.exception("Tarefa %s falhou | id=%s", self.__name__, task_id)
            raise

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(str(uuid.uuid4()), args, kwargs)

    def delay(self, *args: Any, **kwargs: Any) -> TaskHandle:
        task_id = str(uuid.uuid4())
        future = _get_executor().submit(self._run_logged, task_id, args, kwargs)
        return TaskHandle(id=task_id, future=future)


def task(fn: Callable[..., Any] | None = None, *, bind: bool = False):
    """Decorador: `@task` ou `@task(bind=True)`."""
    if fn is not None:
        return Task(fn, bind=False)
    return lambda f: Task(f, bind=bind)
