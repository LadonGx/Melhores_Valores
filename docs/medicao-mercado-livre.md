# Medição do Mercado Livre — como saber se as checagens estão funcionando

Este documento explica como medir a taxa de sucesso das checagens do Mercado Livre (ML) depois
das mudanças de agendamento espaçado, trava única e perfil persistente do navegador
(branch `feat/ml-sem-login-e-formato`).

> **A medição acontece depois do deploy.** Nada aqui deve ser medido antes: sem dados reais
> (`CheckAttempt` vazia) a taxa de sucesso não significa nada.

## 1. Linha de base (antes das mudanças)

Não existia histórico de tentativas — só o diagnóstico manual de **11/11**:

| Rodada | O que aconteceu |
|---|---|
| 09:00 (agendada) | As 9 checagens do ML funcionaram |
| 15:00 (agendada) | **9 de 9 caíram em `login_wall`** (~29 s cada) |
| ~19:00 (botão "Atualizar preço") | Funcionou |

Causa provável nº 1: **rajada**. `schedule_all_products` enfileirava tudo junto e, com
`--concurrency=2`, as 9 páginas do ML abriam em ~1 minuto. Em produção o Beat roda dentro do
worker (`celery worker -B --concurrency=2`).

O que mudou para atacar isso:

- **Agendamento espaçado**: as checagens do ML saem uma a uma, com 60–180 s aleatórios entre
  elas, em ordem embaralhada a cada rodada, dentro de uma janela máxima de 45 min.
- **Trava global**: nunca há 2 checagens do ML ao mesmo tempo (nem worker × worker, nem
  worker × botão da API).
- **Perfil persistente do navegador** e user agent coerente (ver
  `execution/scrapers/README.md`).
- **`CheckAttempt`**: uma linha por checagem real, para medir tudo isso.

## 2. Critério de sucesso

> **O ML precisa ter ≥ 80% de sucesso nas checagens _agendadas_ ao longo de 3 dias.**

Consulta: `GET /stores/stats?days=3&trigger=scheduled` → olhar `success_rate` da loja
`mercadolivre`. Só as agendadas contam: as manuais e as de "anúncio recém-adicionado" têm
comportamento diferente (acontecem quando alguém está olhando, em horários irregulares).

Antes de concluir, confira se `total` é razoável. Com 9 anúncios do ML e Beat a cada 6 h são
~36 checagens por dia, ~108 em 3 dias; um `total` muito abaixo disso indica checagens sendo
perdidas (ver "Se `total` vier baixo" abaixo).

## 3. Lendo `GET /stores/stats`

```
GET /stores/stats?days=7&trigger=scheduled
```

- `days`: 1–90. `trigger` (opcional): `scheduled`, `manual` ou `added`; sem ele, soma todos.
- Sucesso = status `ok`, `out_of_stock` ou `no_offer` (a página foi lida corretamente).
  Falha = `blocked` ou `error`.

```json
{
  "days": 7,
  "since": "2026-11-08T12:00:00+00:00",
  "timezone": "America/Sao_Paulo",
  "trigger": "scheduled",
  "stores": [
    {
      "store": "mercadolivre", "label": "Mercado Livre",
      "total": 63, "successes": 50, "success_rate": 0.7937,
      "by_status": {"ok": 48, "out_of_stock": 1, "no_offer": 1, "blocked": 12, "error": 1},
      "by_block_category": {"login_wall": 12},
      "by_trigger": {"scheduled": 63},
      "by_hour": [{"hour": 0, "total": 0, "successes": 0, "success_rate": null}, "... 24 itens"]
    }
  ]
}
```

Como ler:

| Campo | Para que serve |
|---|---|
| `success_rate` | `successes / total`; `null` quando `total == 0`. É o número do critério (≥ 0,80) |
| `by_status` | Onde estão as falhas: `blocked` (a loja barrou) × `error` (falha nossa/técnica) |
| `by_block_category` | Tipo de bloqueio: `login_wall`, `captcha`, `access_denied`… |
| `by_hour` | Taxa por hora **de Brasília**. Falhas concentradas num horário sugerem rajada ou bloqueio por janela |
| `by_trigger` | Quantas checagens vieram de cada origem (útil sem o filtro `trigger`) |

A lista sempre traz `amazon` e `mercadolivre` (zeradas se não houver linhas) e qualquer outra
loja que tenha tentativas. A Amazon serve de controle: se ela também cai, o problema não é só do ML.

## 4. Consultas SQL de apoio (somente `SELECT`)

Tabela `"CheckAttempt"` (colunas em camelCase, entre aspas). `level`: 1 = httpx, 2 = Playwright,
3 = Firecrawl — em falha, é o último nível tentado. `"durationMs"` é só a checagem (sem a espera
pela trava).

```sql
-- Taxa de sucesso do ML por dia (somente agendadas), últimos 7 dias
SELECT date_trunc('day', "createdAt" AT TIME ZONE 'America/Sao_Paulo') AS dia,
       count(*) AS total,
       count(*) FILTER (WHERE status IN ('ok','out_of_stock','no_offer')) AS sucessos,
       round(100.0 * count(*) FILTER (WHERE status IN ('ok','out_of_stock','no_offer')) / count(*), 1) AS pct
FROM "CheckAttempt"
WHERE store = 'mercadolivre' AND trigger = 'scheduled'
  AND "createdAt" >= now() - interval '7 days'
GROUP BY 1 ORDER BY 1;

-- Falhas do ML por categoria de bloqueio / erro
SELECT status, coalesce("blockCategory", error) AS motivo, count(*)
FROM "CheckAttempt"
WHERE store = 'mercadolivre' AND status IN ('blocked','error')
  AND "createdAt" >= now() - interval '3 days'
GROUP BY 1, 2 ORDER BY 3 DESC;

-- Qual nível da cascata resolve (e quanto demora)
SELECT level, status, count(*), round(avg("durationMs")) AS media_ms
FROM "CheckAttempt"
WHERE store = 'mercadolivre' AND "createdAt" >= now() - interval '3 days'
GROUP BY 1, 2 ORDER BY 1, 2;

-- Intervalo real entre checagens agendadas do ML (deve ficar em ~60–180 s, ou menos se comprimido)
SELECT "createdAt" AT TIME ZONE 'America/Sao_Paulo' AS quando,
       extract(epoch FROM "createdAt" - lag("createdAt") OVER (ORDER BY "createdAt")) AS seg_desde_anterior,
       status, "blockCategory"
FROM "CheckAttempt"
WHERE store = 'mercadolivre' AND trigger = 'scheduled'
  AND "createdAt" >= now() - interval '1 day'
ORDER BY "createdAt";

-- Anúncios que mais falham (podem ser o anúncio, não a loja)
SELECT p.id, p.name, count(*) AS tentativas,
       count(*) FILTER (WHERE a.status IN ('blocked','error')) AS falhas
FROM "CheckAttempt" a JOIN "Product" p ON p.id = a."productId"
WHERE a.store = 'mercadolivre' AND a."createdAt" >= now() - interval '3 days'
GROUP BY 1, 2 ORDER BY falhas DESC;
```

## 5. Se ficar abaixo de 80%

Siga a ordem — do mais barato ao mais invasivo:

1. **Olhe `by_block_category`.** `login_wall` dominante = o ML está barrando o navegador;
   `error` dominante = problema nosso (veja `error` na SQL: `scrape_failed`, `invalid_price`…).
2. **Confirme que o agendamento espaçado está funcionando**: a consulta de intervalos acima
   deve mostrar checagens separadas. Se estiverem coladas, o Beat/worker não está usando o
   código novo.
3. **Falhas concentradas num horário (`by_hour`)**: aumente os intervalos
   (`ML_SCHEDULE_MIN_INTERVAL_S=120`, `ML_SCHEDULE_MAX_INTERVAL_S=300`) e, se precisar, a janela
   (`ML_SCHEDULE_MAX_WINDOW_S`, respeitando o limite do item 6).
4. **Perfil do navegador contaminado**: apague o diretório do perfil (`BROWSER_PROFILE_DIR`,
   padrão `/app/.browser-profile` no container) e reinicie — ele é recriado e reaquecido.
5. **Falhas só em alguns anúncios**: veja a última consulta; pode ser um anúncio específico
   (fora do ar, sem oferta), e não um bloqueio.
6. **`total` vier baixo**: cheque `docker-compose logs worker` por `Loja ocupada — reagendando` e
   `retries esgotados` (trava ocupada demais) e se o worker está de pé durante toda a janela.
7. Só então considere mudanças maiores (reduzir a frequência do Beat para o ML, outro IP/rede).
   O Firecrawl **não** resolve `login_wall` e continua sendo último recurso.

## 6. Variáveis de ambiente (todas opcionais)

| Variável | Padrão | O que faz |
|---|---|---|
| `ML_SCHEDULE_MIN_INTERVAL_S` | `60` | Menor intervalo entre duas checagens agendadas do ML |
| `ML_SCHEDULE_MAX_INTERVAL_S` | `180` | Maior intervalo |
| `ML_SCHEDULE_MAX_WINDOW_S` | `2700` | Teto da janela total da rodada do ML; se a soma dos intervalos passar, eles são comprimidos proporcionalmente (continuam aleatórios e crescentes) |
| `ML_LOCK_TIMEOUT_S` | `300` | Expiração da trava global do ML (proteção contra processo morto) |
| `BROWSER_PROFILE_DIR` | `.browser-profile` | Perfis persistentes do navegador (ver `execution/scrapers/README.md`) |

Validação: valores não numéricos, não positivos ou com mínimo > máximo descartam a configuração
de agendamento inteira e voltam aos padrões (com aviso no log). Também volta aos padrões uma
janela que, somada ao `ML_LOCK_TIMEOUT_S`, passe do `visibility_timeout` do broker.

**Por que 2700 s?** O Redis reentrega mensagens sem ack após o `visibility_timeout` (3600 s,
declarado em `worker_tasks.py`). Tarefas com `countdown` ficam reservadas até o horário; por isso
`janela + ML_LOCK_TIMEOUT_S` precisa ficar abaixo de 3600 s (há teste automático disso).

## 7. Como a trava e as esperas funcionam

- A cascata inteira de cada checagem do ML roda dentro de uma trava no Redis (`store_lock:mercadolivre`).
  Só o ML usa trava; a Amazon passa direto.
- **Botão "Atualizar preço" (`manual`)**: espera até ~60 s pela trava; se esgotar, a API responde
  `reason: "busy"` ("Outra verificação do Mercado Livre está em andamento").
- **Agendada / recém-adicionada**: a task espera até 240 s. Se esgotar, ela se reagenda
  (`retry`) em 60–180 s aleatórios, até 3 vezes; depois desiste da rodada (`reason: "busy"`) e
  tenta de novo na próxima. Trava ocupada **não** gera linha em `CheckAttempt` nem altera a
  "última verificação" — nenhuma checagem real aconteceu.
- **Redis fora do ar**: a checagem segue **sem trava**, com aviso no log
  (`Trava da loja indisponível ... SEM trava`). Sem Redis o cache e o broker também falham, então
  isso só acontece em falha parcial; o perfil do navegador tem sua própria proteção.
