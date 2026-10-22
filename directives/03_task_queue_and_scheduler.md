# Diretiva 03: Task Queue and Scheduler

> Na branch `exe` o Celery (worker + Beat) e o Redis saíram (Fase 4 do `docs/plano-executavel.md`). Tudo roda num processo só.

## Fila de tarefas (`execution/task_runner.py`)

- Tarefas em background são funções decoradas com `@task` (ou `@task(bind=True)` quando precisam do próprio id) em `worker_tasks.py`.
- `minha_task.delay(...)` enfileira num `ThreadPoolExecutor` de **2 threads** e devolve `TaskHandle(id, future)`. Chamar a função direto executa na thread atual.
- Com `bind=True`, `self.request.id` é o mesmo `id` devolvido pelo `.delay()`; é assim que `task_search_products` usa o id da tarefa como `search_id`.
- Exceções são registradas no log com o id da tarefa. `process_price_check` ainda converte exceções num dict `{"status": "error", ...}`.
- Ao fechar o app, o que estava na fila é descartado. Por isso as tarefas precisam ser idempotentes: a próxima checagem refaz o trabalho.
- Scraping (httpx/Playwright) nunca roda na thread do event loop: use uma `@task` ou `asyncio.to_thread`.

## Agendamento (`execution/scheduler.py`)

- APScheduler (`BackgroundScheduler`, UTC) roda `run_full_check` → `schedule_all_products()` **a cada 6 horas**.
- O app só agenda enquanto está aberto. Por isso o horário da última checagem completa fica em `AppMeta.last_full_check` (SQLite). Ao abrir, a próxima rodada fica em última + 6h; se esse horário já passou, roda 1 minuto depois da abertura.
- `schedule_all_products()` ignora produtos `paused` e passa nome/imagem atuais como fallback.
- Quem liga e desliga o agendador é o `lifespan` do `web_server.py`.
