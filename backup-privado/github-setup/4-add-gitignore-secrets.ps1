# SrRobs - 4) So acrescenta .gitignore para bloquear segredos no GIT (nao apaga nada em D:\)
# Corre em D:\Portfolio\github-setup: .\4-add-gitignore-secrets.ps1
# Ele CLONA cada repo temporariamente, adiciona .gitignore reforçado, commit e push.
# NADA e apagado nas tuas pastas D:\ - so no GitHub.

$ErrorActionPreference = "Continue"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SrRobs - Reforcar .gitignore no GitHub (sem tocar em D:\)" -ForegroundColor Cyan
Write-Host " Bloqueia: .env, keys, tokens, ips, db, shots (so no git)" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$token = Read-Host "Cola o ghp_... e pressiona ENTER"
$token = $token.Trim()
if (-not $token) { Write-Host "[ERRO] Token vazio" -ForegroundColor Red; pause; exit 1 }

$user = "robertoMF170"
$setupDir = $PSScriptRoot
$tmpRoot = Join-Path $env:TEMP "srrobs-gitignore-fix"
if (Test-Path $tmpRoot) { Remove-Item $tmpRoot -Recurse -Force }
New-Item -ItemType Directory -Path $tmpRoot | Out-Null

# .gitignore reforçado (comum a todos)
$commonIgnore = @(
  "# === SrRobs - segredos: so no git, nao em D:\ ===",
  ".env",
  ".env.*",
  "*.env",
  "config/glm.properties",
  "config/*.properties",
  "ngrok_domain.txt",
  "farmer_config.json",
  "*token*",
  "*secret*",
  "*api_key*",
  "*apikey*",
  "__pycache__/",
  ".venv/",
  "venv/",
  "node_modules/",
  "*.log",
  "events.db",
  "debug.txt",
  "shots/",
  "baus_cache.json",
  "baus_history.json",
  ".DS_Store",
  "Thumbs.db"
) -join "`n"

$repos = @(
  "srrobs-skin-trader-pro",
  "steamgamessnipe-free-games",
  "robos-farmer-cs2",
  "okx-supertrend-scanner",
  "pinecode-confluence-engine",
  "kronos-klines-ai",
  "fimathe-cycle-pcm",
  "pokemmo-srrobs",
  "bets-converter-paqbet",
  "mt2robs-lite",
  "tbh-toolkit-5contas",
  "csgo500-sessao-500-lab",
  "srrobs-portfolio"
)

foreach ($repo in $repos) {
  Write-Host ""
  Write-Host "=== $repo" -ForegroundColor Cyan
  $work = Join-Path $tmpRoot $repo
  New-Item -ItemType Directory -Path $work | Out-Null
  Push-Location $work
  try {
    $cloneUrl = "https://$token@github.com/$user/$repo.git"
    git clone $cloneUrl . 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] Clone falhou para $repo" -ForegroundColor Red; continue }
    git branch -M main 2>$null | Out-Null

    # Escreve .gitignore reforçado (merge se ja existir)
    $giPath = ".gitignore"
    $existing = ""
    if (Test-Path $giPath) { $existing = Get-Content $giPath -Raw }
    # Se ja tem .env, nao duplica
    if ($existing -notmatch "\.env") {
      $commonIgnore | Out-File $giPath -Encoding utf8 -Append
      Write-Host "[GITIGNORE] Reforcado" -ForegroundColor Gray
    } else {
      # Acrescenta só o que falta (config, ngrok, farmer_config)
      $toAdd = @()
      if ($existing -notmatch "glm.properties") { $toAdd += "config/glm.properties" }
      if ($existing -notmatch "ngrok_domain") { $toAdd += "ngrok_domain.txt" }
      if ($existing -notmatch "farmer_config") { $toAdd += "farmer_config.json" }
      if ($toAdd.Count -gt 0) {
        "" | Out-File $giPath -Append -Encoding utf8
        $toAdd | Out-File $giPath -Append -Encoding utf8
        Write-Host "[GITIGNORE] Acrescentado: $($toAdd -join ', ')" -ForegroundColor Gray
      } else {
        Write-Host "[INFO] .gitignore ja ok" -ForegroundColor Gray
      }
    }

    # Remove do index se algum segredo ja tiver sido commitado antes (so no git, nao em D:\)
    $secrets = @(".env", "config/glm.properties", "ngrok_domain.txt", "farmer_config.json", "events.db", "debug.txt", "shots", "baus_cache.json", ".venv", "node_modules")
    foreach ($s in $secrets) {
      git rm --cached -r --quiet $s 2>$null | Out-Null
    }

    git add .gitignore
    git add -A
    $status = git status --porcelain
    if (-not $status) { Write-Host "[INFO] Sem alteracoes para $repo" -ForegroundColor Gray; continue }
    git commit -m "chore: harden .gitignore - block .env/keys/tokens/ips/db (git only, D:\ intact)" | Out-Null
    git push origin main
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] Push falhou para $repo" -ForegroundColor Red } else { Write-Host "[OK] $repo .gitignore enviado." -ForegroundColor Green }
  } finally { Pop-Location }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " DONE - 13 repos com .gitignore reforçado (so no GitHub)" -ForegroundColor Cyan
Write-Host " D:\ intacto - nada apagado localmente." -ForegroundColor Green
Write-Host " Verifica: https://github.com/robertoMF170" -ForegroundColor Cyan
Write-Host " Prazo: apaga o token em github.com/settings/tokens" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
pause
