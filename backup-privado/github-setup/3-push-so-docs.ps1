# SrRobs - 3) Push SOMENTE documentacao (sem codigo privado)
# Este script substitui o 2-push-all-12.ps1 quando NAO queres subir codigo.
# Ele cria/atualiza cada repo com APENAS: README.md + CREDITS.md + .gitignore + requirements/package stub
# Corre em D:\Portfolio\github-setup: .\3-push-so-docs.ps1
$ErrorActionPreference = "Continue"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SrRobs - Push SOMENTE docs (sem codigo privado)" -ForegroundColor Cyan
Write-Host " Apenas README + creditos + como instalar - sem .env/shots/db" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$token = Read-Host "Cola o ghp_... e pressiona ENTER (ou vazio se ja com gh auth)"
$token = $token.Trim()
$user = "robertoMF170"
$setupDir = $PSScriptRoot

# stubs minimos por repo - nao expoe nada privado
$map = @(
  @{repo="srrobs-skin-trader-pro"; readme="01-srrobs-skin-trader-pro-README.md"; stub="requirements.txt"; stubContent="flask`napscheduler`nrequests`npython-dotenv`nbrotli`npytest`n# config em .env (STEAM_API_KEY, CSFLOAT_KEY, etc) - nao versionar`n"},
  @{repo="steamgamessnipe-free-games"; readme="02-steamgamessnipe-free-games-README.md"; stub="package.json"; stubContent='{ "name": "steamgamessnipe-free-games", "version": "2.0.0", "engines": {"node": ">=20"}, "dependencies": {"discord.js": "^14", "better-sqlite3": "^9", "winston": "^3"} }'},
  @{repo="robos-farmer-cs2"; readme="03-robos-farmer-cs2-README.md"; stub="requirements.txt"; stubContent="customtkinter`npsutil`npillow`npyserial`n# vgamepad opcional`n"},
  @{repo="okx-supertrend-scanner"; readme="04-okx-supertrend-scanner-README.md"; stub="requirements.txt"; stubContent="fastapi`nuvicorn`nhttpx`nnumpy`npandas`njinja2`n"},
  @{repo="pinecode-confluence-engine"; readme="05-pinecode-confluence-engine-README.md"; stub="NOTES.md"; stubContent="# Confluence Engine`nFicheiros Pine/MQL5/user.js nao versionados aqui - importa manualmente no TradingView/MT5/Tampermonkey.`n"},
  @{repo="kronos-klines-ai"; readme="06-kronos-klines-ai-README.md"; stub="requirements.txt"; stubContent="torch`ntransformers`nccxt`nflask`nplotly`npandas`nnumpy`n# modelos em huggingface NeoQuasar/Kronos`n"},
  @{repo="fimathe-cycle-pcm"; readme="07-fimathe-cycle-pcm-README.md"; stub="NOTES.md"; stubContent="# Fimathe Cycle + PCM`nStrategy Pine v6 - cola fimathe-pcm-strategy.pine no TradingView.`n"},
  @{repo="pokemmo-srrobs"; readme="08-pokemmo-srrobs-README.md"; stub="requirements.txt"; stubContent="pyautogui`npillow`npytesseract`npywin32`n# Tesseract OCR requerido no SO`n"},
  @{repo="bets-converter-paqbet"; readme="09-bets-converter-paqbet-README.md"; stub="requirements.txt"; stubContent="flask`nflask-cors`nrequests`nbeautifulsoup4`n"},
  @{repo="mt2robs-lite"; readme="10-mt2robs-lite-README.md"; stub="NOTES.md"; stubContent="# MT2Robs Lite`nRequer eXLib.mix compativel com o teu cliente Gameforge. Nao inclui .mix.`n"},
  @{repo="tbh-toolkit-5contas"; readme="11-tbh-toolkit-5contas-README.md"; stub="requirements.txt"; stubContent="mss`nnumpy`npillow`npywin32`n"},
  @{repo="csgo500-sessao-500-lab"; readme="12-csgo500-sessao-500-lab-README.md"; stub="NOTES.md"; stubContent="# Laboratorio Sessao 500`nAbre painel-sessao.html offline. Vigia requer opencv-python + mss.`n"},
  @{repo="srrobs-portfolio"; readme="13-srrobs-portfolio-README.md"; stub=".gitignore"; stubContent="node_modules/`n.env`n"}
)

# Atualiza README Kronos e MT2 com creditos se ainda nao tem
$kronosReadme = Join-Path $setupDir "readmes\06-kronos-klines-ai-README.md"
if (Test-Path $kronosReadme) {
  $k = Get-Content $kronosReadme -Raw
  if ($k -notmatch "Creditos") {
    $credKronos = "`n## Creditos`n`nBase: NeoQuasar - Kronos - The First K-Line Foundation Model - https://github.com/NeoQuasar/Kronos - HF NeoQuasar/Kronos - AAAI 2026, arXiv 2508.02739. O meu repo e wrapper/adaptacao SrRobs em cima do modelo original.`n"
    Add-Content $kronosReadme $credKronos
    Write-Host "[CREDITS] Kronos README atualizado com base NeoQuasar" -ForegroundColor Gray
  }
}
$mt2Readme = Join-Path $setupDir "readmes\10-mt2robs-lite-README.md"
if (Test-Path $mt2Readme) {
  $m = Get-Content $mt2Readme -Raw
  if ($m -notmatch "Creditos") {
    $credMt2 = "`n## Creditos`n`nBase: eXLib - loader .mix da comunidade Metin2. MT2Robs Lite e minha versao/adaptacao em cima dele (Energy Bot + Locator). O eXLib original nao e meu.`n"
    Add-Content $mt2Readme $credMt2
    Write-Host "[CREDITS] MT2Robs README atualizado com base eXLib" -ForegroundColor Gray
  }
}

# Para cada repo, clona temp, injeta docs, push
$tmpRoot = Join-Path $env:TEMP "srrobs-docs-push"
if (Test-Path $tmpRoot) { Remove-Item $tmpRoot -Recurse -Force }
New-Item -ItemType Directory -Path $tmpRoot | Out-Null

foreach ($m in $map) {
  $repo = $m.repo
  $readmeSrc = Join-Path $setupDir "readmes\$($m.readme)"
  Write-Host ""
  Write-Host "=== $repo" -ForegroundColor Cyan
  if (-not (Test-Path $readmeSrc)) { Write-Host "[AVISO] README nao encontrado: $readmeSrc" -ForegroundColor Yellow; continue }

  $work = Join-Path $tmpRoot $repo
  New-Item -ItemType Directory -Path $work | Out-Null
  Push-Location $work
  try {
    $cloneUrl = if ($token) { "https://$token@github.com/$user/$repo.git" } else { "https://github.com/$user/$repo.git" }
    git clone $cloneUrl . 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
      Write-Host "[ERRO] Clone falhou para $repo - verifica token" -ForegroundColor Red
      continue
    }
    git branch -M main 2>$null | Out-Null

    # Limpa tudo exceto .git, mas mantem README/CREDITS
    Get-ChildItem -Force | Where-Object { $_.Name -ne ".git" } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    # README
    Copy-Item $readmeSrc "README.md" -Force
    # CREDITS global se existir
    $creditsSrc = Join-Path $setupDir "CREDITS.md"
    if (Test-Path $creditsSrc) { Copy-Item $creditsSrc "CREDITS.md" -Force }

    # stub
    if ($m.stub -and $m.stubContent) {
      $m.stubContent | Out-File $m.stub -Encoding utf8
    }
    # .gitignore seguro
    @("__pycache__/", ".venv/", "venv/", "node_modules/", ".env", "*.log", "events.db", "debug.txt", "shots/", "baus_cache.json", ".DS_Store") | Out-File ".gitignore" -Encoding utf8

    git add -A
    $status = git status --porcelain
    if (-not $status) {
      Write-Host "[INFO] $repo ja esta com docs atuais - sem push." -ForegroundColor Gray
      continue
    }
    git commit -m "docs: README detalhado + creditos (sem codigo privado) - $repo" | Out-Null
    git push origin main
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] Push falhou para $repo" -ForegroundColor Red } else { Write-Host "[OK] $repo docs enviados." -ForegroundColor Green }
  } finally { Pop-Location }
}

# Portfolio: push docs + site se ja estiver em D:\Portfolio
$portfolioSrc = Split-Path $setupDir -Parent
$portfolioRepo = "srrobs-portfolio"
$readmePortfolio = Join-Path $setupDir "readmes\13-srrobs-portfolio-README.md"
Write-Host ""
Write-Host "=== $portfolioRepo (portfolio site)" -ForegroundColor Cyan
$work = Join-Path $tmpRoot $portfolioRepo
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Path $work | Out-Null
Push-Location $work
try {
  $cloneUrl = if ($token) { "https://$token@github.com/$user/$portfolioRepo.git" } else { "https://github.com/$user/$portfolioRepo.git" }
  git clone $cloneUrl . 2>&1 | Out-Null
  Get-ChildItem -Force | Where-Object { $_.Name -ne ".git" } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  if (Test-Path $readmePortfolio) { Copy-Item $readmePortfolio "README.md" -Force }
  $creditsSrc = Join-Path $setupDir "CREDITS.md"
  if (Test-Path $creditsSrc) { Copy-Item $creditsSrc "CREDITS.md" -Force }
  # Copia site se existir em portfolioSrc
  foreach ($f in @("index.html","style.css","app.js")) {
    $src = Join-Path $portfolioSrc $f
    if (Test-Path $src) { Copy-Item $src "." -Force; Write-Host "[SITE] $f copiado" -ForegroundColor Gray }
  }
  @("node_modules/", ".env", ".DS_Store") | Out-File ".gitignore" -Encoding utf8
  git add -A
  $status = git status --porcelain
  if ($status) {
    git commit -m "feat: portfolio site + docs (preto/branco/vermelho)" | Out-Null
    git push origin main
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] Portfolio push falhou" -ForegroundColor Red } else { Write-Host "[OK] $portfolioRepo enviado." -ForegroundColor Green }
  } else { Write-Host "[INFO] Portfolio ja atualizado." -ForegroundColor Gray }
} finally { Pop-Location }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " FIM - 13 repos com SOMENTE docs (sem codigo privado)" -ForegroundColor Cyan
Write-Host " Verifica em https://github.com/robertoMF170" -ForegroundColor Cyan
Write-Host " Depois apaga o token em github.com/settings/tokens" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
pause
