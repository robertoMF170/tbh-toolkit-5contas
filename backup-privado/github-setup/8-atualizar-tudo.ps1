# ============================================================
#  8-atualizar-tudo.ps1  -  SrRobs
#  Atualiza TODOS os repos Git + o site (portfolio) num so sitio.
#
#  O que faz:
#    1) RELATORIO - estado atual de cada projeto (commits, alteracoes)
#    2) SEGURANCA - esconde contas / emails / tokens / apis antes do push
#    3) README    - injeta descricao facil de ler se faltar
#    4) PUSH      - commit + push de tudo (token NUNCA fica guardado)
#
#  Modos:
#    [1] Analisar tudo  (so relatorio, sem push)
#    [2] Novo push      (analisa + commit + push de tudo)
#    [3] Auto           (novo push automatico em loop)
#    [Q] Sair
# ============================================================

$ErrorActionPreference = "Continue"

# ---------------- configuracao ----------------
$GitUser   = "robertoMF170"
$GitName   = "SrRobs"
$GitEmail  = "roberto@srrobs.dev"
$SetupDir  = $PSScriptRoot
$ReadmeDir = Join-Path $SetupDir "readmes"

$AutoIntervalSec = 300   # modo auto: 5 minutos entre pushes

# portfolio (o site) = pasta pai desta pasta github-setup
$PortfolioSrc  = Split-Path $SetupDir -Parent
$PortfolioRepo = "srrobs-portfolio"

# -------- mapa dos 12 projetos (pasta -> repo -> readme) --------
$Map = @(
    @{ src = "D:\cs2snipre";                           repo = "srrobs-skin-trader-pro";     readme = "01-srrobs-skin-trader-pro-README.md" },
    @{ src = "D:\steamgamessnipe";                     repo = "steamgamessnipe-free-games"; readme = "02-steamgamessnipe-free-games-README.md" },
    @{ src = "D:\CS2BotImprover";                      repo = "robos-farmer-cs2";           readme = "03-robos-farmer-cs2-README.md" },
    @{ src = "D:\okx";                                 repo = "okx-supertrend-scanner";     readme = "04-okx-supertrend-scanner-README.md" },
    @{ src = "D:\pinecode";                            repo = "pinecode-confluence-engine"; readme = "05-pinecode-confluence-engine-README.md" },
    @{ src = "D:\kronos";                              repo = "kronos-klines-ai";           readme = "06-kronos-klines-ai-README.md" },
    @{ src = "D:\FIMAYHE PCM";                         repo = "fimathe-cycle-pcm";          readme = "07-fimathe-cycle-pcm-README.md" },
    @{ src = "D:\pokemmo";                             repo = "pokemmo-srrobs";             readme = "08-pokemmo-srrobs-README.md" },
    @{ src = "D:\coversorbets";                        repo = "bets-converter-paqbet";      readme = "09-bets-converter-paqbet-README.md" },
    @{ src = "D:\metin2\MT2Robs-Lite";                 repo = "mt2robs-lite";               readme = "10-mt2robs-lite-README.md" },
    @{ src = "D:\tbh 2";                               repo = "tbh-toolkit-5contas";        readme = "11-tbh-toolkit-5contas-README.md" },
    @{ src = "D:\csgo500 vamos ser ricos com a sorte"; repo = "csgo500-sessao-500-lab";     readme = "12-csgo500-sessao-500-lab-README.md" }
)

# -------- gitignore por repo (regras extra do 5-limpar-expostos) --------
$ExtraIgnore = @{
    "tbh-toolkit-5contas"     = @("baus.json", "baus_historico.json", "abrir_conta*.bat", "capturas/", "*.es3", "Sandboxie_*.ini")
    "bets-converter-paqbet"   = @("ngrok_domain.txt")
    "robos-farmer-cs2"        = @("build/", "dist/", "agent_out/", "agent_err/")
    "pinecode-confluence-engine" = @(".freebuff/")
    "kronos-klines-ai"        = @(".freebuff/")
    "srrobs-skin-trader-pro"  = @("app.log", "app.err.log")
}

# -------- gitignore comum (2-push + 5-limpar) --------
$GitignoreBase = @(
    "node_modules/", ".env", "*.env",
    "baus.json", "baus_historico.json", "*.es3",
    ".freebuff/", ".DS_Store", "Thumbs.db",
    "app.log", "app.err.log", "ngrok_domain.txt",
    "__pycache__/", "*.pyc", ".venv/", "venv/",
    "capturas/"
)

# ---------------- helpers ----------------
function Write-Banner($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Write-Ok($t)     { Write-Host "  [OK] $t" -ForegroundColor Green }
function Write-Warn2($t)  { Write-Host "  [!]  $t" -ForegroundColor Yellow }
function Write-Erro($t)   { Write-Host "  [X]  $t" -ForegroundColor Red }
function Write-Info($t)   { Write-Host "  .    $t" -ForegroundColor Gray }

function Test-Git {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Erro "Git nao encontrado. Instala o Git for Windows primeiro."
        pause; exit 1
    }
}

function Set-GitConfig {
    git config --global user.name  $GitName  2>$null
    git config --global user.email $GitEmail 2>$null
}

# token: so e pedido quando ha push; nunca e gravado em ficheiro nenhum
function Get-Token {
    $t = Read-Host "Cola o token ghp_... (ENTER = usar credenciais ja guardadas)"
    return $t.Trim()
}

# ============================================================
#  SCANNER DE SEGREDOS - procura contas/tokens/apis/especies no index
#  Corre DEPOIS do 'git add' e ANTES do commit/push.
#  Se apanha algo: tira do commit, mete no .gitignore e avisa.
# ============================================================
$SecretNamePatterns = @(".env", "*.es3", "baus.json", "baus_historico.json", "ngrok_domain.txt", "Sandboxie_*.ini", "abrir_conta*.bat", "capturas/")
$SecretContentRegex = '(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i)(api_key|apikey|secret|password|passwd|token)\s*[=:]\s*["''][^"'']{8,}|[A-Za-z0-9._%+-]+@proton\.me|[A-Za-z0-9._%+-]+@protonmail\.com)'

function Test-IndexSecrets {
    # 1) nomes de ficheiros perigosos no index
    $bad = @()
    $files = git diff --cached --name-only 2>$null
    foreach ($f in $files) {
        $leaf = Split-Path $f -Leaf
        foreach ($p in $SecretNamePatterns) {
            if ($leaf -like $p) { $bad += $f; break }
        }
        if ($f -match '(^|/)capturas/') { $bad += $f }
    }
    # 2) conteudo: tokens/chaves/emails nos ficheiros ja em staging
    if (-not $bad) {
        $hits = git grep -I --cached -n -E $SecretContentRegex 2>$null
        if ($hits) {
            $badFiles = $hits | ForEach-Object { ($_ -split ":")[0] } | Select-Object -Unique
            $bad += $badFiles
            Write-Warn2 "Conteudo com segredo detetado em: $($badFiles -join ', ')"
        }
    }
    return ($bad | Select-Object -Unique)
}

function Protect-Secrets($srcPath, $repo) {
    # devolve $true se ficou limpo, $false se ainda ha perigo
    $bad = Test-IndexSecrets
    if (-not $bad) { return $true }
    foreach ($f in $bad) {
        Write-Warn2 "A ESCONDER (nunca vai para o GitHub): $f"
        git reset -q HEAD -- "$("$f" -replace '/','\')" 2>$null
    }
    # reforca o .gitignore com o que foi apanhado
    $gi = Join-Path $srcPath ".gitignore"
    $lines = @()
    if (Test-Path $gi) { $lines = Get-Content $gi }
    foreach ($f in $bad) {
        $leaf = Split-Path $f -Leaf
        if ($lines -notcontains $leaf) {
            if ($f -match '(^|/)capturas/') { $leaf = "capturas/" }
            $lines += $leaf
        }
    }
    $lines | Set-Content $gi -Encoding UTF8
    git add -A 2>$null
    # segunda verificacao
    $bad2 = Test-IndexSecrets
    if ($bad2) {
        Write-Erro "Ainda ha segredos em staging: $($bad2 -join ', ')"
        Write-Erro "Corre o 5-limpar-expostos.ps1 / 6-rewrite-history.ps1 deste projeto."
        return $false
    }
    Write-Ok "Segredos escondidos via .gitignore"
    return $true
}

# ============================================================
#  GITIGNORE + README
# ============================================================
function Ensure-Gitignore($srcPath, $repo) {
    $gi = Join-Path $srcPath ".gitignore"
    $want = @($GitignoreBase)
    if ($ExtraIgnore.ContainsKey($repo)) { $want += $ExtraIgnore[$repo] }
    $existing = @()
    if (Test-Path $gi) { $existing = @(Get-Content $gi | Where-Object { $_ -ne "" }) }
    $missing = $want | Where-Object { $existing -notcontains $_ }
    if ($missing) {
        ($existing + $missing) | Set-Content $gi -Encoding UTF8
        Write-Info ".gitignore atualizado (+$($missing.Count) regras)"
    }
}

function Ensure-Readme($srcPath, $readmeFile) {
    $target = Join-Path $srcPath "README.md"
    if (Test-Path $target) { return }
    $src = Join-Path $ReadmeDir $readmeFile
    if (Test-Path $src) {
        Copy-Item $src $target -Force
        Write-Info "README.md injetado (descricao facil de ler)"
    } else {
        $placeholder = "# Projeto`n`nDescricao breve em construcao. - SrRobs`n"
        [IO.File]::WriteAllText($target, $placeholder)
        Write-Info "README.md criado (placeholder)"
    }
}

# ============================================================
#  RELATORIO DE ESTADO por projeto
# ============================================================
function Show-Status($srcPath, $repo) {
    Write-Host ""
    Write-Host "---- $repo ----" -ForegroundColor Cyan
    if (-not (Test-Path $srcPath)) { Write-Warn2 "Pasta nao existe: $srcPath (saltado)"; return }
    Push-Location $srcPath
    try {
        if (-not (Test-Path (Join-Path $srcPath ".git"))) { Write-Info "Ainda nao e repo Git (vai ser iniciado no push)"; return }
        $last = git log -1 --oneline 2>$null
        if ($last) { Write-Info "Ultimo commit: $last" } else { Write-Info "Sem commits ainda" }
        $st = git status --porcelain 2>$null
        $n = @($st).Count
        if ($n -gt 0) {
            Write-Warn2 "$n ficheiro(s) alterados/por commitar"
            $st | Select-Object -First 8 | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
        } else { Write-Ok "Tudo commitado (arquivo limpo)" }
        if (git remote 2>$null | Select-String -Quiet "origin") {
            git fetch -q origin 2>$null
            $ahead  = git rev-list --count origin/main..HEAD 2>$null
            $behind = git rev-list --count HEAD..origin/main 2>$null
            if ($ahead -gt 0)  { Write-Warn2 "$ahead commit(s) a frente do GitHub (precisa push)" }
            if ($behind -gt 0) { Write-Warn2 "$behind commit(s) atras do GitHub (precisa pull)" }
        } else { Write-Info "Sem remote origin (o push cria)" }
        # resumo do README (descricao facil de digerir)
        $rm = Join-Path $srcPath "README.md"
        if (Test-Path $rm) {
            $title = (Get-Content $rm | Where-Object { $_ -match '\S' } | Select-Object -First 1)
            if ($title) { Write-Info "Descricao: $($title -replace '#','').Trim()" }
        }
    } finally { Pop-Location }
}

# ============================================================
#  PUSH de um repo: init + seguranca + commit + push + limpar token
# ============================================================
function Push-One($srcPath, $repo, $readmeFile, $token) {
    Write-Host ""
    Write-Host "==== $repo ====" -ForegroundColor Cyan
    if (-not (Test-Path $srcPath)) { Write-Warn2 "Pasta nao existe: $srcPath (saltado)"; return $false }
    Push-Location $srcPath
    try {
        if (-not (Test-Path ".git")) {
            git init 2>&1 | Out-Null
            git branch -M main 2>&1 | Out-Null
        }
        Ensure-Readme $srcPath $readmeFile
        Ensure-Gitignore $srcPath $repo
        git add -A 2>&1 | Out-Null
        if (-not (Protect-Secrets $srcPath $repo)) { return $false }

        $cleanUrl = "https://github.com/$GitUser/$repo.git"
        if ($token) {
            git remote remove origin 2>$null
            git remote add origin "https://$token@github.com/$GitUser/$repo.git"
        } elseif (git remote 2>$null | Select-String -Quiet "origin") {
            git remote set-url origin $cleanUrl 2>$null
        } else {
            Write-Erro "Sem token e sem origin guardado - usa o modo [2] e cola o token"
            return $false
        }

        $hasHead = git rev-parse -q --verify HEAD 2>$null
        $staged  = @(git diff --cached --name-only 2>$null)
        if (-not $hasHead) {
            if ($staged.Count -eq 0) {
                New-Item -ItemType File -Path (Join-Path $srcPath ".gitkeep") -Force | Out-Null
                git add -A 2>&1 | Out-Null
            }
            git commit -m "init: $repo (primeiro commit) - SrRobs" 2>&1 | Out-Null
        } elseif ($staged.Count -gt 0) {
            git commit -m "update: $repo $(Get-Date -Format 'yyyy-MM-dd HH:mm')" 2>&1 | Out-Null
        } else {
            Write-Info "Nada novo para commitar"
        }

        git push -u origin main --force 2>&1 | Out-Host
        if ($LASTEXITCODE -eq 0) {
            git remote set-url origin $cleanUrl 2>$null   # TIRA o token do remote
            Write-Ok "Push OK -> github.com/$GitUser/$repo"
            return $true
        }
        Write-Erro "Push falhou. Manual: cd '$srcPath'; git push -u origin main --force"
        return $false
    } finally { Pop-Location }
}

function Push-All($token) {
    $ok = 0
    foreach ($m in $Map) { if (Push-One $m.src $m.repo $m.readme $token) { $ok++ } }
    # o SITE (portfolio) tambem entra no push
    if (Push-One $PortfolioSrc $PortfolioRepo "13-srrobs-portfolio-README.md" $token) { $ok++ }
    Write-Banner "FEITO: $ok repo(s) atualizado(s)"
    Write-Warn2 "Quando terminares: revoga o token no GitHub (Settings > Developer settings)"
}

function Analyze-All {
    Write-Banner "ESTADO ATUAL DOS PROJETOS"
    foreach ($m in $Map) { Show-Status $m.src $m.repo }
    Show-Status $PortfolioSrc "$PortfolioRepo (o SITE)"
}

# ============================================================
#  ARRANQUE + MENU  (aceita escrever 'novo push' ou 'analisar')
# ============================================================
Test-Git
Set-GitConfig
Write-Banner "8-atualizar-tudo - SrRobs"
Write-Host "  [1] Analisar tudo (so relatorio)" -ForegroundColor White
Write-Host "  [2] Novo push  (analisa + esconde segredos + push de tudo)" -ForegroundColor White
Write-Host "  [3] Auto       (novo push automatico de $AutoIntervalSec em $AutoIntervalSec seg)" -ForegroundColor White
Write-Host "  [Q] Sair" -ForegroundColor White

while ($true) {
    $c = (Read-Host "Escreve").Trim().ToLower()
    if     ($c -eq "q" -or $c -eq "sair")      { break }
    elseif ($c -eq "1" -or $c -like "*analisar*") { Analyze-All }
    elseif ($c -eq "2" -or $c -like "*push*") {
        $tok = Get-Token
        Analyze-All
        Push-All $tok
    }
    elseif ($c -eq "3" -or $c -like "*auto*") {
        $tok = Get-Token
        while ($true) {
            Analyze-All
            Push-All $tok
            Write-Host ""
            Write-Host "Proximo push automatico em $AutoIntervalSec s (Ctrl+C para parar)..." -ForegroundColor DarkGray
            Start-Sleep -Seconds $AutoIntervalSec
        }
    }
    else { Write-Warn2 "Opcao? [1] [2] [3] [Q]  (ou escreve 'novo push')" }
}
