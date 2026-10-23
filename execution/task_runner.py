"""
Filas de tarefas em threads, no lugar do Celery worker.

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

# Duas filas, para uma ação do usuário (adicionar produto, buscar) nunca esperar
# atrás de uma checagem em lote (20 produtos × até 30 s cada):
#   "user"       → o que o usuário acabou de pedir e está esperando na tela
#   "background" → checagens em lote (automática de 6 h e "Atualizar todos")
# Cada fila tem 2 threads, como o --concurrency=2 do antigo worker Celery.
QUEUES = {"user": 2, "background": 2}
DEFAULT_QUEUE = "user"
MAX_WORKERS = QUEUES[DEFAULT_QUEUE]

_executors: dict[str, ThreadPoolExecutor] = {}
_executor_lock = threading.Lock()


def _get_executor(queue: str = DEFAULT_QUEUE) -> ThreadPoolExecutor:
    if queue not in QUEUES:
        raise ValueError(f"Fila desconhecida: {queue!r} (use {', '.join(QUEUES)})")
    with _executor_lock:
        if queue not in _executors:
            _executors[queue] = ThreadPoolExecutor(
                max_workers=QUEUES[queue], thread_name_prefix=f"mv-{queue}"
            )
        return _executors[queue]


def shutdown(wait: bool = False) -> None:
    """Encerra as filas (no fechamento do app). Tarefas ainda na fila são descartadas."""
    with _executor_lock:
        for executor in _executors.values():
            executor.shutdown(wait=wait, cancel_futures=True)
        _executors.clear()


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
        """Enfileira na fila do usuário (a padrão)."""
        return self.apply_async(args, kwargs)

    def apply_async(self, args: tuple = (), kwargs: dict | None = None, queue: str = DEFAULT_QUEUE) -> TaskHandle:
        """Como no Celery: permite escolher a fila (`queue="background"` para lotes)."""
        task_id = str(uuid.uuid4())
        future = _get_executor(queue).submit(self._run_logged, task_id, tuple(args), kwargs or {})
        return TaskHandle(id=task_id, future=future)


def task(fn: Callable[..., Any] | None = None, *, bind: bool = False):
    """Decorador: `@task` ou `@task(bind=True)`."""
    if fn is not None:
        return Task(fn, bind=False)
    return lambda f: Task(f, bind=bind)
