# SrRobs — 5) Limpar dados pessoais expostos no GitHub (rode no Windows)
#
# O QUE FAZ (só no GitHub; as tuas pastas em D:\ ficam intactas):
#   tbh-toolkit-5contas      -> REMOVE: baus.json, baus_historico.json, abrir_conta*.bat,
#                               baus_para_importar/ (saves .es3), Sandboxie_*.ini, capturas *.png,
#                               *.estado.txt, alertas_dedup.json, analysis_result.json, game_manifest.acf
#   bets-converter-paqbet    -> REMOVE: ngrok_domain.txt   | ADD: ngrok_domain.example.txt
#   robos-farmer-cs2         -> REMOVE: build/ inteira, agent_out.txt, agent_err.txt
#   pinecode-confluence-eng. -> REMOVE: .freebuff/ (DB do Freebuff)
#   kronos-klines-ai         -> REMOVE: .freebuff/ (DB do Freebuff)
#   srrobs-skin-trader-pro   -> REMOVE: app.log, app.err.log
#
# IMPORTANTE: rewrite_history.ps1 (passo 6) e OBRIGATORIO para o TBH —
# apagar ficheiros num commit novo NAO apaga o historico; os saves .es3
# continuam acessiveis em commits antigos.
#
# Uso: powershell -ExecutionPolicy Bypass -File .\5-limpar-expostos.ps1
#      (pede o ghp_... no inicio e apaga-o do clipboard no fim)

$ErrorActionPreference = "Continue"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SrRobs - Limpar dados pessoais expostos (GitHub, D:\ intacto)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$token = Read-Host "Cola o ghp_... (classic, scope repo) e pressiona ENTER"
$token = $token.Trim()
if (-not $token) { Write-Host "[ERRO] Token vazio" -ForegroundColor Red; pause; exit 1 }

$user = "robertoMF170"
$tmpRoot = Join-Path $env:TEMP "srrobs-limpeza"
if (Test-Path $tmpRoot) { Remove-Item $tmpRoot -Recurse -Force }
New-Item -ItemType Directory -Path $tmpRoot | Out-Null

# git identity sem email pessoal
git config --global user.name  "SrRobs" 2>$null
git config --global user.email "SrRobsParecias@proton.me" 2>$null

# gitignore reforçado para repos de codigo (TBH fica para o passo 6)
$commonIgnore = @(
  "__pycache__/", ".venv/", "venv/", "node_modules/",
  ".env", ".env.*", "*.env",
  "*.log", "events.db", "debug.txt", "shots/",
  "ngrok_domain.txt", "farmer_config.json", "config/glm.properties",
  "baus.json", "baus_historico.json", "baus_cache.json", "*.es3",
  ".freebuff/", ".DS_Store", "Thumbs.db"
) -join "`n"

# mapa: repo -> ficheiros/pastas a remover do repo (lista vazia = so gitignore)
$removals = @{
  "tbh-toolkit-5contas" = @(
    "baus.json", "baus_historico.json", "baus_cache.json",
    "abrir_conta1.bat", "abrir_conta2.bat", "abrir_conta3.bat", "abrir_conta4.bat", "abrir_conta5.bat",
    "abrir_todas_contas.bat", "abrir_minhas_builds.bat",
    "baus_para_importar", "Sandboxie_backup.ini", "Sandboxie_utf8.ini",
    "abrir_steam.py.estado.txt", "alertas_dedup.json", "analysis_result.json",
    "game_manifest.acf", "game_version.txt",
    "captura_0_pid5224.png", "captura_1_pid27172.png", "captura_32772.png",
    "ecra_completo.png", "ecra_completo2.png", "ecra_completo3.png"
  )
  "bets-converter-paqbet" = @("ngrok_domain.txt")
  "robos-farmer-cs2"      = @("build", "agent_out.txt", "agent_err.txt", "dist")
  "pinecode-confluence-engine" = @(".freebuff")
  "kronos-klines-ai"      = @(".freebuff")
  "srrobs-skin-trader-pro" = @("app.log", "app.err.log")
}

foreach ($repo in $removals.Keys) {
  Write-Host ""
  Write-Host "=== $repo" -ForegroundColor Cyan
  $work = Join-Path $tmpRoot $repo
  New-Item -ItemType Directory -Path $work | Out-Null
  Push-Location $work
  try {
    git clone "https://$token@github.com/$user/$repo.git" . 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] Clone falhou - verifica token" -ForegroundColor Red; continue }
    git branch -M main 2>$null | Out-Null

    $removed = 0
    foreach ($item in $removals[$repo]) {
      if (Test-Path $item) {
        git rm -r --cached --quiet $item 2>$null | Out-Null   # remove do git, mantem no disco (se existir)
        Remove-Item $item -Recurse -Force -ErrorAction SilentlyContinue  # no clone temporario
        $removed++
      }
    }
    Write-Host "  removidos do git: $removed itens"

    # gitignore reforçado (não duplica)
    $gi = ".gitignore"
    $existing = ""
    if (Test-Path $gi) { $existing = Get-Content $gi -Raw }
    if ($existing -notmatch "\.freebuff|baus\.json|ngrok_domain") {
      if ($existing) { Add-Content $gi $commonIgnore -Encoding utf8 } else { $commonIgnore | Out-File $gi -Encoding utf8 }
      git add .gitignore
    }

    # exemplo de ngrok sem dominio real
    if ($repo -eq "bets-converter-paqbet" -and -not (Test-Path "ngrok_domain.example.txt")) {
      "teu-dominio.ngrok-free.dev" | Out-File "ngrok_domain.example.txt" -Encoding utf8
      git add ngrok_domain.example.txt
    }

    $status = git status --porcelain
    if (-not $status) { Write-Host "[INFO] nada a mudar" -ForegroundColor Gray; continue }
    git commit -m "chore: remove dados pessoais (contas, saves, logs, db) - ver README para setup" | Out-Null
    git push origin main
    if ($LASTEXITCODE -eq 0) { Write-Host "[OK] $repo limpo no HEAD" -ForegroundColor Green }
    else { Write-Host "[ERRO] push falhou para $repo" -ForegroundColor Red }
  } finally { Pop-Location }
}

# limpar token do clipboard (fica na variavel apenas em memoria)
Set-Clipboard -Value "" 2>$null

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " HEAD limpo. MAS o historico antigo ainda tem os .es3/contas." -ForegroundColor Yellow
Write-Host " Passo OBRIGATORIO para o TBH: corre 6-rewrite-history.ps1" -ForegroundColor Yellow
Write-Host " Depois: apaga o token em github.com/settings/tokens" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
pause
