# Troca do anúncio do grupo "Ritmo da Guerra" (Kindle → edição física)

No grupo **"Ritmo da Guerra"**, o anúncio da Amazon monitorado hoje é a edição
**eBook Kindle** (`B0FYGGWCHR` — aparece com o selo **Kindle** na interface). O
livro físico (**Capa Comum**) é `6581339210`.

**Nada é feito agora.** Este passo a passo é para o Guilherme executar
**depois do deploy**. Cada passo tem a versão pela interface (tela) e a
equivalente por `curl` na API do homelab (`http://192.168.0.200:8090/api/...`).
Ao criar/trocar, a interface passa a marcar o Kindle com o selo e mostra o
aviso "Este grupo mistura eBook Kindle e edição física — os preços não são
comparáveis." enquanto os dois estiverem no mesmo grupo (aviso não bloqueante).

> **Por que trocar:** o Kindle e a capa comum são produtos com preços muito
> diferentes; comparar os dois como "mesmo livro" distorce o menor preço do
> grupo. Depois da troca, o grupo fica só com edições físicas comparáveis.

## 1. Adicionar o anúncio físico

**Tela:** página de adicionar produto → colar
`https://www.amazon.com.br/dp/6581339210` → adicionar e esperar a primeira
checagem terminar (aí o formato dele já fica identificado: sem selo Kindle).

**API:**

```sh
curl -X POST http://192.168.0.200:8090/api/monitor/add \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.amazon.com.br/dp/6581339210"}'
```

Conferir que foi monitorado (e ver o `id` dele) — o formato já deve aparecer
como `physical` depois da primeira checagem:

```sh
curl http://192.168.0.200:8090/api/products
```

## 2. Colocar o anúncio novo no grupo

**Tela:** Dashboard → selecionar o grupo "Ritmo da Guerra" **+** o anúncio novo
(pelos checkboxes) → na barra flutuante, clicar em **"Adicionar ao grupo"**.
Enquanto o Kindle ainda estiver no grupo, aparece o aviso de formatos
misturados (não bloqueia; é só para conferir o passo 5). Depois disso:
o anúncio novo aparece **sem selo** e o Kindle **com selo** na linha do grupo
e na tabela de anúncios do modal do grupo.

**API** (o `id` do grupo vem de `GET /groups`; `product_ids` recebe o id do anúncio novo):

```sh
curl http://192.168.0.200:8090/api/groups

curl -X POST http://192.168.0.200:8090/api/groups/<GROUP_ID>/products \
  -H "Content-Type: application/json" \
  -d '{"product_ids": ["<ID_NOVO>"]}'
```

## 3. Tirar o Kindle do grupo

**Tela:** abrir o modal do grupo "Ritmo da Guerra" → na linha do anúncio
**com selo Kindle** (o `B0FYGGWCHR`) → **"Remover do grupo"**.
O grupo continua com o(s) outro(s) anúncio(s).

**API:**

```sh
curl -X DELETE http://192.168.0.200:8090/api/groups/<GROUP_ID>/products/<ID_KINDLE>
```

## 4. Pausar o monitoramento do Kindle

**Tela:** no modal do grupo/anúncio do Kindle, usar o banner de pausa
("Pausar monitoramento"). O histórico de preços dele continua disponível;
nada é apagado.

**API:**

```sh
curl -X PATCH http://192.168.0.200:8090/api/product/<ID_KINDLE>/status \
  -H "Content-Type: application/json" \
  -d '{"status": "paused"}'
```

> **Apagar** o anúncio do Kindle é uma decisão do Guilherme (não é necessário):
> pausado, ele para de consumir checagens mas mantém o histórico. Se decidir
> apagar, o endpoint é `DELETE /api/product/<ID_KINDLE>`.

## 5. Conferir o fim

- **Tela:** o grupo "Ritmo da Guerra" aparece só com o anúncio físico (sem
  selo Kindle, sem aviso de formatos misturados); o Kindle continua na lista
  de anúncios com o selo Kindle e "Pausado".
- **API:**

```sh
# Grupo sem o Kindle e com o físico
curl http://192.168.0.200:8090/api/groups

# kindle pausado (status "paused"), físico com formato "physical" e preço novo
curl http://192.168.0.200:8090/api/products
```
