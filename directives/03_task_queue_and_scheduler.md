# Diretiva 03: Task Queue and Scheduler

> Na branch `exe` o Celery (worker + Beat) e o Redis saíram (Fase 4 do `docs/plano-executavel.md`). Tudo roda num processo só.

## Fila de tarefas (`execution/task_runner.py`)

- Tarefas em background são funções decoradas com `@task` (ou `@task(bind=True)` quando precisam do próprio id) em `worker_tasks.py`.
- Duas filas de **2 threads** cada: `user` (padrão; `minha_task.delay(...)`) para o que o usuário acabou de pedir (busca, adicionar produto) e `background` (`minha_task.apply_async(args, queue="background")`) para lotes. Uma ação do usuário nunca espera atrás de um lote. Ambas devolvem `TaskHandle(id, future)`. Chamar a função direto executa na thread atual.
- Com `bind=True`, `self.request.id` é o mesmo `id` devolvido pelo `.delay()`; é assim que `task_search_products` usa o id da tarefa como `search_id`.
- Exceções são registradas no log com o id da tarefa. `process_price_check` ainda converte exceções num dict `{"status": "error", ...}`.
- Ao fechar o app, o que estava na fila é descartado. Por isso as tarefas precisam ser idempotentes: a próxima checagem refaz o trabalho.
- Scraping (httpx/Playwright) nunca roda na thread do event loop: use uma `@task` ou `asyncio.to_thread`.

## Agendamento (`execution/scheduler.py`)

- APScheduler (`BackgroundScheduler`, UTC) roda `run_full_check` → `schedule_all_products()` **a cada 6 horas**.
- O app só agenda enquanto está aberto. Por isso o horário da última checagem completa fica em `AppMeta.last_full_check` (SQLite). Ao abrir, a próxima rodada fica em última + 6h; se esse horário já passou, roda 1 minuto depois da abertura.
- `schedule_all_products()` cria **um lote** (fila `background`) com progresso em memória (`refresh_status()`), ignora produtos `paused` e passa nome/imagem atuais como fallback. É o mesmo lote do botão "Atualizar todos" (`POST /api/products/refresh-all`, sem cache). Se já houver um lote rodando, não duplica. Grava `AppMeta.last_full_check`.
- Quem liga e desliga o agendador é o `lifespan` do `web_server.py`.
