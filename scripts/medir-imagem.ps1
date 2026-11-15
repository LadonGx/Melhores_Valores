# medir-imagem.ps1 — medição de imagem da API (tempo até subir, RAM em repouso, pico opcional).
#
# Uso (Windows, PowerShell 5.1+, Docker Desktop):
#   .\scripts\medir-imagem.ps1 -Image mv-api:antes
#   .\scripts\medir-imagem.ps1 -Image mv-api:antes -PeakUrl "https://www.amazon.com.br/dp/XXXX"
#
# O que faz, para a imagem passada em -Image:
#   1. cria uma rede propria (mvmed-*) e sobe postgres:15-alpine e redis:7-alpine nela
#      (SEM publicar 5432/6379 no host);
#   2. sobe a API com o comando de PRODUCAO (prisma migrate deploy && uvicorn ...),
#      publicando a porta 8000, com FIRECRAWL_API_KEY vazio; mede o tempo do
#      docker run ate GET / responder 200;
#   3. sobe o worker de PRODUCAO (celery worker -B ...); espera o log "ready" e confere
#      no log que as tarefas foram registradas e que o Beat carregou;
#   4. depois de ~30 s, mede a RAM em repouso da API e do worker (docker stats --no-stream,
#      varias amostras, mediana);
#   5. com -PeakUrl (desligado por padrao): insere um produto com essa URL direto no Postgres,
#      chama POST /product/{id}/refresh e amostra a RAM da API a cada ~0,5 s, guardando o pico
#      e a resposta (fase de medicao real; nao usar para testar "gratis" — e visita real ao site);
#   6. imprime um resumo e derruba TUDO que criou (containers e rede), mesmo com erro.
#
# Depende so de Docker e PowerShell 5.1. Nao publica 5432/6379; publica apenas 8000.

param(
    [Parameter(Mandatory = $true)]
    [string]$Image,

    # Opcional (desligado por padrao). URL de produto para o teste de pico (visita real).
    [string]$PeakUrl
)

$ErrorActionPreference = 'Stop'

# ── nomes unicos desta rodada ─────────────────────────────────────────────────
$stamp  = Get-Date -Format 'yyyyMMddHHmmss'
$net    = "mvmed-net-$stamp"
$dbC    = "mvmed-db-$stamp"
$redisC = "mvmed-redis-$stamp"
$apiC   = "mvmed-api-$stamp"
$workerC = "mvmed-worker-$stamp"

# Tudo que este script criou, para o finally limpar (containers primeiro, rede por ultimo).
$cleanup = @($apiC, $workerC, $dbC, $redisC)

function Remove-TestResources {
    foreach ($c in $cleanup) {
        # -v: apaga junto os volumes anonimos do postgres/redis (senao sobra ~46 MB por rodada)
        cmd /c "docker rm -f -v $c >NUL 2>&1"
    }
    cmd /c "docker network rm $net >NUL 2>&1"
}

# ── helpers ──────────────────────────────────────────────────────────────────
function Write-Step([string]$Message) { Write-Host "[medicao] $Message" }

function Get-ContainerLog([string]$Name) {
    # docker logs escreve em stderr: vai pelo cmd para voltar tudo como texto simples.
    cmd /c "docker logs $Name 2>&1"
}

function ConvertTo-MiB([string]$MemUsage) {
    # "251.7MiB / 3.7GiB" -> 251.7 (so a parte usada)
    if ($MemUsage -match '^\s*([\d.]+)\s*(B|KB|KiB|MB|MiB|GB|GiB|TB|TiB)') {
        $val = [double]$Matches[1]
        switch ($Matches[2]) {
            'B'     { $val = $val / 1MB }
            'KB'    { $val = $val / 1024 }
            'KiB'   { $val = $val / 1024 }
            'MB'    { $val = $val }
            'MiB'   { $val = $val }
            'GB'    { $val = $val * 1024 }
            'GiB'   { $val = $val * 1024 }
            'TB'    { $val = $val * 1024 * 1024 }
            'TiB'   { $val = $val * 1024 * 1024 }
        }
        return [math]::Round($val, 1)
    }
    return 0.0
}

function Get-Median([double[]]$Values) {
    if ($null -eq $Values -or $Values.Count -eq 0) { return 0.0 }
    $sorted = $Values | Sort-Object
    $n = $sorted.Count
    if ($n % 2 -eq 1) { return [math]::Round($sorted[[int](($n - 1) / 2)], 1) }
    return [math]::Round(($sorted[$n / 2 - 1] + $sorted[$n / 2]) / 2, 1)
}

function Get-ContainerMemSamples {
    # Uma rodada de docker stats --no-stream; devolve @{ Nome = MiB } para os containers da rodada.
    $result = @{}
    $lines = cmd /c 'docker stats --no-stream --format "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"'
    foreach ($line in $lines) {
        $parts = $line -split "`t"
        if ($parts.Count -ge 2) {
            $result[$parts[0].Trim()] = ConvertTo-MiB $parts[1]
        }
    }
    return $result
}

function Get-StoreFromUrl([string]$Url) {
    $u = $Url.ToLower()
    if ($u -match 'mercadolivre\.com|mercadolibre\.com|mlstatic\.com') { return 'mercadolivre' }
    if ($u -match 'amazon\.com') { return 'amazon' }
    return 'amazon'  # padrao conservador: a deteccao de loja da API trata o resto
}

$apiSeconds      = $null
$ramApiMiB       = $null
$ramWorkerMiB    = $null
$tasksRegistered = $false
$beatLoaded      = $false
$workerReady     = $false
$peakMiB         = $null
$refreshResult   = $null

try {
    # ── pre-checagens ────────────────────────────────────────────────────────────
    Write-Step "Verificando Docker e imagem '$Image'..."
    cmd /c "docker image inspect $Image >NUL 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "Imagem '$Image' nao existe (docker image inspect falhou)." }

    $listening = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($listening) { throw "Porta 8000 ja esta em uso no host (necessaria para a API de teste)." }

    if ($PeakUrl) {
        Write-Step "ATENCAO: -PeakUrl definido — o teste de pico faz uma visita REAL ao site do anuncio."
    }

    # ── rede + banco + redis (sem publicar 5432/6379) ────────────────────────────
    Write-Step "Criando rede '$net'..."
    docker network create $net | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar a rede $net." }

    Write-Step "Subindo Postgres e Redis (sem portas no host)..."
    docker run -d --name $dbC --network $net `
        -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password -e POSTGRES_DB=price_tracker `
        postgres:15-alpine | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao subir o Postgres." }

    docker run -d --name $redisC --network $net redis:7-alpine | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao subir o Redis." }

    # Espera o Postgres aceitar conexoes (migrate deploy falharia antes disso)
    $dbReady = $false
    for ($i = 0; $i -lt 60; $i++) {
        docker exec $dbC pg_isready -U user -d price_tracker > $null 2>&1
        if ($LASTEXITCODE -eq 0) { $dbReady = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $dbReady) { throw "Postgres nao ficou pronto em 60 s." }
    Write-Step "Postgres pronto."

    # ── API (comando de producao; publica apenas 8000) ───────────────────────────
    Write-Step "Subindo a API ($Image) com prisma migrate deploy && uvicorn..."
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    docker run -d --name $apiC --network $net -p 8000:8000 `
        -e "DATABASE_URL=postgresql://user:password@$($dbC):5432/price_tracker" `
        -e "REDIS_URL=redis://$($redisC):6379/1" `
        -e "FIRECRAWL_API_KEY=" `
        $Image sh -c 'prisma migrate deploy && uvicorn execution.web_server:app --host 0.0.0.0 --port 8000' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao subir a API." }

    # Tempo do docker run ate GET / responder 200
    while ($sw.Elapsed.TotalSeconds -lt 180) {
        try {
            $resp = Invoke-WebRequest -Uri 'http://localhost:8000/' -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200) { break }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    $apiSeconds = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    if (-not $resp -or $resp.StatusCode -ne 200) {
        Write-Step "AVISO: GET / nao respondeu 200 em $apiSeconds s. Log da API:"
        Get-ContainerLog $apiC | Select-Object -Last 20
        throw "API nao ficou pronta em 180 s."
    }
    Write-Step "API respondeu 200 em $apiSeconds s."

    # ── worker (comando de producao, com Beat embutido) ──────────────────────────
    Write-Step "Subindo o worker (celery worker -B, concurrency=2)..."
    docker run -d --name $workerC --network $net `
        -e "DATABASE_URL=postgresql://user:password@$($dbC):5432/price_tracker" `
        -e "REDIS_URL=redis://$($redisC):6379/1" `
        -e "FIRECRAWL_API_KEY=" `
        $Image sh -c 'celery -A execution.worker_tasks worker -B -s /tmp/celerybeat-schedule --concurrency=2 --max-tasks-per-child=20 --loglevel=info' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao subir o worker." }

    # Espera o log "ready" (celery@<host>.ready.)
    for ($i = 0; $i -lt 60; $i++) {
        $log = (Get-ContainerLog $workerC) -join "`n"
        if ($log -match '@[\w.-]+ ready\.') { $workerReady = $true; break }
        Start-Sleep -Seconds 2
    }
    $log = (Get-ContainerLog $workerC) -join "`n"
    $tasksRegistered = ($log -match '\[tasks\]')
    $beatLoaded = ($log -match 'beat: Starting')
    if (-not $workerReady) {
        Write-Step "AVISO: worker nao reportou 'ready' em ~120 s. Ultimas linhas:"
        Get-ContainerLog $workerC | Select-Object -Last 20
    }
    Write-Step ("Worker ready={0} | tarefas registradas={1} | beat carregado={2}" -f `
        $workerReady, $tasksRegistered, $beatLoaded)

    # ── RAM em repouso (~30 s depois, 5 amostras, mediana) ───────────────────────
    Write-Step "Aguardando 30 s para medir a RAM em repouso..."
    Start-Sleep -Seconds 30

    $apiSamples = @()
    $workerSamples = @()
    for ($i = 0; $i -lt 5; $i++) {
        $stats = Get-ContainerMemSamples
        if ($stats.ContainsKey($apiC)) { $apiSamples += [double]$stats[$apiC] }
        if ($stats.ContainsKey($workerC)) { $workerSamples += [double]$stats[$workerC] }
        Start-Sleep -Seconds 2
    }
    $ramApiMiB = Get-Median $apiSamples
    $ramWorkerMiB = Get-Median $workerSamples

    # ── pico (opcional; visita real) ─────────────────────────────────────────────
    if ($PeakUrl) {
        Write-Step "Teste de pico com $PeakUrl ..."
        $productId = [guid]::NewGuid().ToString()
        $store = Get-StoreFromUrl $PeakUrl

        # Insere direto no Postgres (identificadores precisam de aspas duplas; via stdin)
        $sql = "INSERT INTO `"Product`" (id, url, store, `"updatedAt`") VALUES ('$productId', '$PeakUrl', '$store', NOW());"
        $sql | docker exec -i $dbC psql -U user -d price_tracker
        if ($LASTEXITCODE -ne 0) { throw "Falha ao inserir o produto de teste no Postgres." }

        # Amostra a RAM da API a cada ~0,5 s enquanto o refresh roda (job em background)
        $refreshUrl = "http://localhost:8000/product/$productId/refresh"
        $job = Start-Job -ScriptBlock {
            param($Url)
            try {
                $r = Invoke-WebRequest -Uri $Url -Method Post -Body '{}' -ContentType 'application/json' -UseBasicParsing -TimeoutSec 300
                "HTTP $($r.StatusCode)"
                $r.Content
            } catch {
                "ERRO: $($_.Exception.Message)"
            }
        } -ArgumentList $refreshUrl

        $peakMiB = 0.0
        while ($job.State -eq 'Running') {
            $stats = Get-ContainerMemSamples
            if ($stats.ContainsKey($apiC) -and [double]$stats[$apiC] -gt $peakMiB) {
                $peakMiB = [double]$stats[$apiC]
            }
            Start-Sleep -Milliseconds 500
        }
        $refreshResult = (Receive-Job $job -Wait) -join ' | '
        Remove-Job $job -Force | Out-Null
        $peakMiB = [math]::Round($peakMiB, 1)
        Write-Step "Resposta do refresh: $refreshResult | Pico de RAM da API: $peakMiB MiB"
    }

    # ── resumo ───────────────────────────────────────────────────────────────────
    Write-Host ""
    Write-Host "==================== RESUMO DA MEDICAO ===================="
    Write-Host "Imagem:                  $Image"
    Write-Host "Tempo ate GET / (200):   $apiSeconds s"
    Write-Host "RAM repouso API:         $ramApiMiB MiB (mediana de $($apiSamples.Count) amostras)"
    Write-Host "RAM repouso worker:      $ramWorkerMiB MiB (mediana de $($workerSamples.Count) amostras)"
    Write-Host "Worker:                  ready=$workerReady | tasks=$tasksRegistered | beat=$beatLoaded"
    if ($PeakUrl) {
        Write-Host "Pico RAM API (refresh):  $peakMiB MiB"
        Write-Host "Resposta do refresh:     $refreshResult"
    }
    Write-Host "==========================================================="
}
catch {
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Write-Step "Removendo containers e rede de teste..."
    Remove-TestResources
}
