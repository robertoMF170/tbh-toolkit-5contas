# SrRobs - 2/2 Push 12 projetos de D:\ para GitHub (PowerShell)
$ErrorActionPreference = "Continue"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SrRobs - 2/2 Push 12 projetos de D:\ para GitHub" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Verifica git e configura identity se faltar
try { $null = Get-Command git -ErrorAction Stop } catch {
  Write-Host "[ERRO] git nao encontrado. Instala https://git-scm.com/download/win" -ForegroundColor Red
  pause; exit 1
}
Write-Host "[OK] git encontrado: $(git --version)" -ForegroundColor Green

# Garante git config global (evita src refspec main does not match any)
$gitName = git config --global user.name 2>$null
$gitEmail = git config --global user.email 2>$null
if (-not $gitName) { git config --global user.name "SrRobs"; Write-Host "[GIT] user.name = SrRobs" -ForegroundColor Gray }
if (-not $gitEmail) { git config --global user.email "roberto@srrobs.dev"; Write-Host "[GIT] user.email = roberto@srrobs.dev" -ForegroundColor Gray }
Write-Host "[GIT] $($gitName) <$($gitEmail)>" -ForegroundColor Gray

$token = Read-Host "Cola o ghp_... para push (mesmo de antes) e pressiona ENTER"
$token = $token.Trim()
if (-not $token) { Write-Host "[AVISO] Sem token - vou tentar sem auth" -ForegroundColor Yellow }

$user = "robertoMF170"
$setupDir = $PSScriptRoot

$map = @(
  @{src="D:\cs2snipre"; repo="srrobs-skin-trader-pro"; readme="01-srrobs-skin-trader-pro-README.md"},
  @{src="D:\steamgamessnipe"; repo="steamgamessnipe-free-games"; readme="02-steamgamessnipe-free-games-README.md"},
  @{src="D:\CS2BotImprover"; repo="robos-farmer-cs2"; readme="03-robos-farmer-cs2-README.md"},
  @{src="D:\okx"; repo="okx-supertrend-scanner"; readme="04-okx-supertrend-scanner-README.md"},
  @{src="D:\pinecode"; repo="pinecode-confluence-engine"; readme="05-pinecode-confluence-engine-README.md"},
  @{src="D:\kronos"; repo="kronos-klines-ai"; readme="06-kronos-klines-ai-README.md"},
  @{src="D:\FIMAYHE PCM"; repo="fimathe-cycle-pcm"; readme="07-fimathe-cycle-pcm-README.md"},
  @{src="D:\pokemmo"; repo="pokemmo-srrobs"; readme="08-pokemmo-srrobs-README.md"},
  @{src="D:\coversorbets"; repo="bets-converter-paqbet"; readme="09-bets-converter-paqbet-README.md"},
  @{src="D:\metin2\MT2Robs-Lite"; repo="mt2robs-lite"; readme="10-mt2robs-lite-README.md"},
  @{src="D:\tbh 2"; repo="tbh-toolkit-5contas"; readme="11-tbh-toolkit-5contas-README.md"},
  @{src="D:\csgo500 vamos ser ricos com a sorte"; repo="csgo500-sessao-500-lab"; readme="12-csgo500-sessao-500-lab-README.md"}
)

function Push-One($src, $repo, $readmeFile) {
  Write-Host ""
  Write-Host "=== $repo <= $src" -ForegroundColor Cyan
  if (-not (Test-Path $src)) {
    Write-Host "[AVISO] Pasta nao encontrada: $src -- a saltar." -ForegroundColor Yellow
    return
  }
  Push-Location $src
  try {
    if ($token) { $url = "https://$token@github.com/$user/$repo.git" } else { $url = "https://github.com/$user/$repo.git" }

    # git config local tambem (caso nao tenha global)
    $localEmail = git config user.email 2>$null
    if (-not $localEmail) {
      git config user.name "SrRobs" 2>$null | Out-Null
      git config user.email "roberto@srrobs.dev" 2>$null | Out-Null
    }

    if (-not (Test-Path ".git")) {
      git init | Out-Null
      git branch -M main 2>$null | Out-Null
    } else {
      git branch -M main 2>$null | Out-Null
    }

    if (-not (Test-Path "README.md")) {
      $readmeSrc = Join-Path $setupDir "readmes\$readmeFile"
      if (Test-Path $readmeSrc) { Copy-Item $readmeSrc "README.md" -Force; Write-Host "[README] Injetado $readmeFile" -ForegroundColor Gray }
    }
    if (-not (Test-Path ".gitignore")) {
      @("__pycache__/", ".venv/", "venv/", "node_modules/", ".env", "*.log", "events.db", "debug.txt", "shots/", "baus_cache.json", "config/glm.properties", "ngrok_domain.txt", "farmer_config.json") | Out-File ".gitignore" -Encoding utf8
      Write-Host "[GITIGNORE] Criado com segredos bloqueados (so no git)" -ForegroundColor Gray
    }

    git remote remove origin 2>$null | Out-Null
    git remote add origin $url 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { git remote set-url origin $url 2>$null | Out-Null }

    git add -A
    $commitOut = git commit -m "chore: initial import - $repo (SrRobs)" 2>&1
    $commitCode = $LASTEXITCODE
    if ($commitCode -ne 0) {
      # Pode ser "nothing to commit" mas pode ter sido por falta de staged changes
      $porcelain = git status --porcelain 2>$null
      if (-not $porcelain) {
        Write-Host "[INFO] Nada novo para commit (working tree clean)." -ForegroundColor Gray
        # Mas ainda precisamos garantir que existe commit em main
        $hasCommit = git rev-parse --verify HEAD 2>$null
        if (-not $hasCommit) {
          Write-Host "[FIX] Sem commit em HEAD -- criando commit vazio com README" -ForegroundColor Yellow
          if (-not (Test-Path "README.md")) { "Placeholder" | Out-File "README.md" -Encoding utf8 }
          git add README.md .gitignore 2>$null | Out-Null
          git commit -m "docs: initial import - $repo" 2>&1 | Out-Null
        }
      } else {
        Write-Host "[COMMIT] $commitOut" -ForegroundColor Yellow
      }
    } else {
      Write-Host "[COMMIT] $commitOut" -ForegroundColor Gray
    }

    Write-Host "[PUSH] origin main --force ..." -ForegroundColor Gray
    git push -u origin main --force 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
      Write-Host "[ERRO] Push falhou para $repo. Verifica token / rede." -ForegroundColor Red
      Write-Host "       Tenta manual: cd `"$src`" ; git push -u origin main --force" -ForegroundColor Yellow
    } else {
      Write-Host "[OK] $repo enviado." -ForegroundColor Green
      git remote set-url origin "https://github.com/$user/$repo.git" 2>$null | Out-Null
    }
  } finally { Pop-Location }
}

foreach ($m in $map) { Push-One $m.src $m.repo $m.readme }

# Portfolio - D:\Portfolio
Write-Host ""
Write-Host "--- Portfolio (este site) ---" -ForegroundColor Cyan
$portfolioSrc = Split-Path $setupDir -Parent
if (-not (Test-Path (Join-Path $portfolioSrc "index.html"))) { $portfolioSrc = Get-Location }
Write-Host "Portfolio src: $portfolioSrc" -ForegroundColor Gray
Push-Location $portfolioSrc
try {
  if ($token) { $url = "https://$token@github.com/$user/srrobs-portfolio.git" } else { $url = "https://github.com/$user/srrobs-portfolio.git" }
  $localEmail = git config user.email 2>$null
  if (-not $localEmail) { git config user.name "SrRobs" 2>$null | Out-Null; git config user.email "roberto@srrobs.dev" 2>$null | Out-Null }
  if (-not (Test-Path ".git")) { git init | Out-Null; git branch -M main 2>$null | Out-Null } else { git branch -M main 2>$null | Out-Null }
  $readmePortfolio = Join-Path $setupDir "readmes\13-srrobs-portfolio-README.md"
  if (-not (Test-Path "README.md") -and (Test-Path $readmePortfolio)) { Copy-Item $readmePortfolio "README.md" -Force; Write-Host "[README] Injetado portfolio" -ForegroundColor Gray }
  if (-not (Test-Path ".gitignore")) { @("node_modules/", ".env") | Out-File ".gitignore" -Encoding utf8 }
  git remote remove origin 2>$null | Out-Null
  git remote add origin $url 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { git remote set-url origin $url 2>$null | Out-Null }
  git add -A
  if (Test-Path "index.html") { git add index.html style.css app.js 2>$null | Out-Null }
  $commitOut = git commit -m "feat: SrRobs portfolio - ewan-kerboas inspired (preto/branco/vermelho)" 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Host "[INFO] Nada novo para commit portfolio." -ForegroundColor Gray }
  else { Write-Host "[COMMIT] $commitOut" -ForegroundColor Gray }
  git push -u origin main --force 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] Portfolio push falhou." -ForegroundColor Red } else { Write-Host "[OK] srrobs-portfolio enviado." -ForegroundColor Green; git remote set-url origin "https://github.com/$user/srrobs-portfolio.git" 2>$null | Out-Null }
} finally { Pop-Location }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " FIM - verifica em https://github.com/robertoMF170" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
pause
