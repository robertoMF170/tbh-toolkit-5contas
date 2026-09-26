# SrRobs - Criar static.yml para GitHub Pages (Static HTML)
# Corre em D:\Portfolio\github-setup: .\Criar-static-yml.ps1
# Cria .github/workflows/static.yml local, commit e push para srrobs-portfolio

$ErrorActionPreference = "Stop"

$portfolioDir = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path (Join-Path $portfolioDir "index.html"))) {
  Write-Host "[ERRO] Nao encontrei index.html em $portfolioDir" -ForegroundColor Red
  Write-Host "Abre o PowerShell dentro de D:\Portfolio\github-setup" -ForegroundColor Yellow
  pause; exit 1
}

$workflowDir = Join-Path $portfolioDir ".github\workflows"
New-Item -ItemType Directory -Path $workflowDir -Force | Out-Null

$ymlPath = Join-Path $workflowDir "static.yml"
@"
# Simple workflow for deploying static content to GitHub Pages
name: Deploy static content to Pages

on:
  # Runs on pushes targeting the default branch
  push:
    branches: ["main"]
  # Allows you to run this workflow manually from the Actions tab
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: `${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Pages
        uses: actions/configure-pages@v5
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: '.'
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v5
"@ | Out-File $ymlPath -Encoding utf8

Write-Host "[OK] Criado $ymlPath" -ForegroundColor Green
Get-Content $ymlPath | Write-Host -ForegroundColor Gray

# Ativa Pages via API se tiveres token - opcional
$token = Read-Host "Cola o ghp_... para push + ativar Pages (ou ENTER para so criar local)"
$token = $token.Trim()

Push-Location $portfolioDir
try {
  git add ".github/workflows/static.yml"
  $status = git status --porcelain
  if (-not $status) {
    Write-Host "[INFO] Sem alteracoes - static.yml ja commitado" -ForegroundColor Yellow
  } else {
    git commit -m "ci: add Pages static.yml (Static HTML) for srrobs-portfolio"
    Write-Host "[OK] Commitado" -ForegroundColor Green
  }

  if ($token) {
    $user = "robertoMF170"
    $repo = "srrobs-portfolio"
    Write-Host "[PUSH] origin main..." -ForegroundColor Gray
    $url = "https://$token@github.com/$user/$repo.git"
    git remote remove origin 2>$null | Out-Null
    git remote add origin $url 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { git remote set-url origin $url | Out-Null }
    git push origin main
    if ($LASTEXITCODE -ne 0) {
      Write-Host "[ERRO] Push falhou - verifica token" -ForegroundColor Red
    } else {
      Write-Host "[OK] Push feito" -ForegroundColor Green
      git remote set-url origin "https://github.com/$user/$repo.git" | Out-Null
      Write-Host ""
      Write-Host "Ativando GitHub Pages (actions) via API..." -ForegroundColor Gray
      $headers = @{ Authorization = "Bearer $token"; Accept = "application/vnd.github+json" }
      $body = @{ source = @{ branch = "main"; path = "/" } } | ConvertTo-Json
      # Tenta API de Pages com source actions
      $pagesBody = @{ build_type = "workflow" } | ConvertTo-Json
      try {
        # Cria/ativa Pages com GitHub Actions como source
        Invoke-RestMethod -Uri "https://api.github.com/repos/$user/$repo/pages" -Headers $headers -Method Post -Body $pagesBody 2>$null | Out-Null
        Write-Host "[OK] Pages ativado (workflow)" -ForegroundColor Green
      } catch {
        $code = 0; try { $code = $_.Exception.Response.StatusCode.Value__ } catch {}
        if ($code -eq 409) {
          # Ja existe - atualiza
          try { Invoke-RestMethod -Uri "https://api.github.com/repos/$user/$repo/pages" -Headers $headers -Method Put -Body $pagesBody | Out-Null; Write-Host "[OK] Pages atualizado para workflow" -ForegroundColor Green } catch { Write-Host "[AVISO] Pages ja existe mas PUT falhou: $($_.Exception.Message)" -ForegroundColor Yellow }
        } elseif ($code -eq 404) {
          Write-Host "[AVISO] Pages API 404 - ativa manual em Settings > Pages > Source: GitHub Actions" -ForegroundColor Yellow
        } else {
          Write-Host "[AVISO] Pages API falhou ($code): $($_.Exception.Message)" -ForegroundColor Yellow
          Write-Host "       Ativa manual: https://github.com/$user/$repo/settings/pages -> Source: GitHub Actions" -ForegroundColor Yellow
        }
      }
    }
    Write-Host ""
    Write-Host "Live em ~2min: https://robertoMF170.github.io/srrobs-portfolio/" -ForegroundColor Cyan
    Write-Host "Actions: https://github.com/$user/$repo/actions" -ForegroundColor Cyan
  } else {
    Write-Host ""
    Write-Host "[INFO] Sem token - faz push manual:" -ForegroundColor Yellow
    Write-Host "  cd `"$portfolioDir`"" -ForegroundColor White
    Write-Host "  git push origin main" -ForegroundColor White
    Write-Host "Depois ativa Pages manual: https://github.com/robertoMF170/srrobs-portfolio/settings/pages -> Source: GitHub Actions" -ForegroundColor Yellow
  }
} finally { Pop-Location }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " DONE - static.yml pronto" -ForegroundColor Cyan
Write-Host " Site: https://robertoMF170.github.io/srrobs-portfolio/" -ForegroundColor Cyan
Write-Host " Para GitHub falar PT: Settings > Pages > Source: GitHub Actions" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
pause
