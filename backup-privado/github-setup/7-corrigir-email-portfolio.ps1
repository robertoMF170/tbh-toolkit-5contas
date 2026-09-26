# SrRobs — 7) Corrigir email pessoal no historico do PORTFOLIO
#
# O commit "Create static.yml" foi feito pela interface web do GitHub e ficou
# com o autor  robertosdac@gmail.com  (visivel na API de commits).
# Isto reescreve o historico para esse email passar a ser o Proton.
#
# REQUISITO: pip install git-filter-repo  (instala sozinho se faltar)
#
# Uso: powershell -ExecutionPolicy Bypass -File .\7-corrigir-email-portfolio.ps1
#      corre DENTRO da pasta do portfolio (a que tem o index.html)

$ErrorActionPreference = "Continue"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SrRobs - Corrigir email pessoal no historico (portfolio)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# confirma que estamos na pasta certa
if (-not (Test-Path "index.html")) {
  Write-Host "[ERRO] Corre este script dentro da pasta do portfolio (index.html)" -ForegroundColor Red
  pause; exit 1
}
if (-not (Test-Path ".git")) {
  Write-Host "[ERRO] Esta pasta nao e um repo git" -ForegroundColor Red
  pause; exit 1
}

# mostrar o problema antes
Write-Host "Autores atuais no historico:" -ForegroundColor Gray
git log --format="%h %an <%ae>" | Sort-Object -Unique
Write-Host ""

# identity nova
git config user.name  "SrRobs"
git config user.email "SrRobsParecias@proton.me"

# garantir git-filter-repo
$hasFilterRepo = $false
try { git filter-repo --version 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $hasFilterRepo = $true } } catch {}
if (-not $hasFilterRepo) {
  Write-Host "git-filter-repo nao encontrado - a instalar via pip..." -ForegroundColor Gray
  pip install git-filter-repo 2>&1 | Out-Null
  try { git filter-repo --version 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $hasFilterRepo = $true } } catch {}
}
if (-not $hasFilterRepo) {
  Write-Host "[ERRO] instala Python + 'pip install git-filter-repo' e volta a correr" -ForegroundColor Red
  pause; exit 1
}

# reescrever emails + nomes em TODO o historico
git filter-repo --force --email-callback "
return b'SrRobsParecias@proton.me' if email == b'robertosdac@gmail.com' else email
" --name-callback "
return b'SrRobs'
"
if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] filter-repo falhou" -ForegroundColor Red; pause; exit 1 }

# filter-repo remove o remote - repor (sem token; usa credential manager)
git remote add origin "https://github.com/robertoMF170/srrobs-portfolio.git" 2>$null | Out-Null

Write-Host ""
Write-Host "Autores DEPOIS da reescrita:" -ForegroundColor Gray
git log --format="%h %an <%ae>" | Sort-Object -Unique
Write-Host ""

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Historico reescrito localmente. Falta o push forcado:" -ForegroundColor Yellow
Write-Host "   git push origin main --force" -ForegroundColor White
Write-Host "" -ForegroundColor Cyan
Write-Host " (GitHub Pages volta a deployar sozinho depois do push)" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan
pause
