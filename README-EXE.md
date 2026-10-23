# Melhores Valores — versão para Windows (.exe)

Versão de **teste** do Melhores Valores que roda inteira no seu computador: é só baixar, extrair e abrir. Não precisa de Docker, banco de dados, Python nem Node, e não depende de nenhum servidor.

> Esta é uma versão à parte. A versão web/servidor continua descrita no [README.md](README.md).

## Versão web × versão .exe

| | Versão web (servidor) | Versão .exe (esta) |
| --- | --- | --- |
| Onde roda | Servidor com Docker (PostgreSQL, Redis, Celery) | No seu Windows, num programa só |
| Seus dados | No banco do servidor | Num arquivo no seu computador |
| Checagem automática de preços | 24 h por dia | A cada 6 h **enquanto o app está aberto** (e ao abrir, se já passou da hora) |
| Navegador usado no scraping | Chromium no container | O **Microsoft Edge** do seu Windows (ou o Chrome, se o Edge falhar) |
| Firecrawl (API paga) | Chave do servidor | Opcional, com a **sua** chave |

## Requisitos

- Windows 10 ou 11, 64 bits.
- Microsoft Edge (já vem no Windows) e o componente WebView2 (também já vem no Windows 11 e nas versões atuais do 10).
- Internet.

## Instalar e abrir

1. Baixe o arquivo `MelhoresValores-vX.Y.Z-windows.zip` na página de **Releases** do repositório.
2. Extraia o `.zip` para uma pasta sua, por exemplo `C:\Users\<você>\Programas\MelhoresValores`.
3. Abra `MelhoresValores.exe`.

**Aviso do Windows (SmartScreen):** como o executável não é assinado digitalmente, o Windows pode mostrar "O Windows protegeu o computador". Clique em **Mais informações** e depois em **Executar assim mesmo**. Isso só aparece na primeira vez.

O app abre numa janela própria. Ela pode ser minimizada, maximizada e fechada como qualquer programa. **Fechar a janela encerra o app.** Abrir o app de novo enquanto ele já está aberto só traz a janela para frente.

## Primeiro uso

O app começa **vazio**: nenhum produto, nenhum histórico. Para começar a monitorar:

- **Buscar produto**: digite o nome (ex.: "echo dot"). Os resultados da Amazon e do Mercado Livre aparecem ordenados por preço. Clique em **Monitorar** no que quiser acompanhar.
- **Produtos → + Adicionar URL**: cole o link de um anúncio da Amazon ou do Mercado Livre.

Tudo o que você adicionar **fica salvo** até você mesmo excluir, inclusive depois de fechar o app, reiniciar o computador ou atualizar para uma versão nova.

## Atualizar os preços

- **Automático:** a cada 6 horas, enquanto o app está aberto. Se você abrir o app e a última checagem tiver sido há mais de 6 horas, ele checa sozinho 1 minuto depois de abrir.
- **Atualizar todos** (Dashboard e Produtos): checa de novo todos os produtos ativos agora. O botão mostra o progresso (ex.: "Atualizando 3/21…") e, no fim, um resumo de quantos foram atualizados.
- **Atualizar preço agora** (dentro dos detalhes de um produto) ou **Atualizar preço** (na lista de Produtos): checa só aquele produto. Gráfico e estatísticas se atualizam na hora.
- Buscar ou adicionar um produto nunca espera uma checagem em andamento: as ações que você faz têm uma fila própria.

Produtos **pausados** ficam fora das checagens, mas o histórico continua guardado.

## Onde ficam os seus dados

Tudo fica em `%LOCALAPPDATA%\MelhoresValores\` (cole esse caminho na barra do Explorador de Arquivos):

| Arquivo/pasta | O que é |
| --- | --- |
| `melhores_valores.db` | Seus produtos, histórico de preços e buscas (banco SQLite) |
| `webview\` | Dados da janela do app (grupos de produtos, filtros do dashboard) |
| `logs\app.log` | Registro do que o app fez (útil para relatar problemas) |
| `config.env` | Configuração opcional (você cria; ver abaixo) |

- **Backup:** feche o app e copie a pasta inteira.
- **Atualizar de versão:** baixe o `.zip` novo e substitua a pasta do programa. A pasta de dados não é tocada.
- **Desinstalar:** apague a pasta do programa. Para apagar também os seus dados, apague `%LOCALAPPDATA%\MelhoresValores\`.

## Firecrawl (opcional, pago)

Quando a Amazon ou o Mercado Livre bloqueiam a leitura da página, o app pode recorrer ao [Firecrawl](https://firecrawl.dev), um serviço pago. Isso é **desligado por padrão**. Para ligar, crie o arquivo `%LOCALAPPDATA%\MelhoresValores\config.env` com:

```
FIRECRAWL_API_KEY="sua-chave-aqui"
```

e reabra o app. Cada uso consome créditos da **sua** conta. Sem a chave, o app funciona normalmente, só sem esse último recurso.

## Limitações conhecidas

- As checagens automáticas só acontecem com o app aberto.
- O **Mercado Livre** às vezes exige login para mostrar anúncios e buscas ("login wall"). Quando isso acontece, o app avisa ("Mercado Livre está temporariamente exigindo login…") e mostra os resultados das outras lojas. Trocar de navegador não resolve; normalmente passa sozinho depois de um tempo.
- A Amazon às vezes mostra ofertas diferentes para o mesmo produto, então o preço pode alternar entre dois valores de um dia para o outro.
- Só Windows por enquanto.

## Solução de problemas

| Problema | O que fazer |
| --- | --- |
| A janela não abre ou fica em branco | Verifique se o Microsoft Edge está atualizado (o WebView2 vem junto). Sem WebView2, o app abre no navegador padrão. |
| "Porta ocupada" / outro programa na mesma porta | O app escolhe outra porta sozinho e passa a usar sempre a mesma. Para forçar uma porta: `MelhoresValores.exe --port 9000`. |
| Um produto nunca atualiza | Abra os detalhes e use **Atualizar preço agora**: a mensagem diz se a loja bloqueou ou se o anúncio saiu do ar. |
| Quero relatar um erro | Envie o arquivo `%LOCALAPPDATA%\MelhoresValores\logs\app.log`. |

Opções de linha de comando: `--browser` abre no navegador padrão em vez da janela; `--port N` escolhe a porta.

## Para desenvolvedores

Código na branch `exe`. Plano e histórico de decisões em [docs/plano-executavel.md](docs/plano-executavel.md).

```powershell
pnpm install
pip install -r requirements.txt -r requirements-dev.txt
pnpm build
python main.py                                                      # rodar do código (janela nativa)
powershell -ExecutionPolicy Bypass -File scripts\build_desktop.ps1  # gerar dist\MelhoresValores\MelhoresValores.exe
```

- O build falha se aparecer `.env` ou banco de dados dentro de `dist\`: o executável nunca leva dados ou chaves do desenvolvedor.
- `MV_DATA_DIR=<pasta>` troca a pasta de dados, para testar sem misturar com a sua.
- `scripts/copy_web_data.py` copia (só lendo) os dados da versão web para um banco de teste.
- **Release:** atualize `__version__` em `execution/__init__.py`, crie a tag `vX.Y.Z` igual e faça push da tag. O workflow `.github/workflows/build-desktop.yml` testa, gera o `.zip` e cria um Release **em rascunho**, que você revisa e publica no GitHub.
