# SrRobs - 1/2 PowerShell (ASCII only)
$ErrorActionPreference = "Stop"
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SrRobs - Criar 13 repos + apagar Spoon-Knife (PowerShell)" -ForegroundColor Cyan
Write-Host " Precisas de token Classic ghp_... com repo + delete_repo" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
$token = Read-Host "Cola o teu ghp_... (classic) e pressiona ENTER"
$token = $token.Trim()
if (-not $token) { Write-Host "[ERRO] Token vazio" -ForegroundColor Red; pause; exit 1 }
if (-not $token.StartsWith("ghp_")) { Write-Host "[AVISO] Nao comeca com ghp_ - deve ser fine-grained, vai dar 403" -ForegroundColor Yellow }
$headers = @{ Authorization = "Bearer $token"; Accept = "application/vnd.github+json"; "User-Agent" = "SrRobs-setup" }
Write-Host ""
Write-Host "[1/4] A verificar autenticacao..." -ForegroundColor Gray
try {
  $me = Invoke-RestMethod -Uri "https://api.github.com/user" -Headers $headers -Method Get
  Write-Host "OK - autenticado como $($me.login) ($($me.name))" -ForegroundColor Green
} catch {
  Write-Host "[ERRO] Falha auth: $($_.Exception.Message)" -ForegroundColor Red
  if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message -ForegroundColor Red }
  Write-Host "Dica: cria token em https://github.com/settings/tokens/new -> Generate new token (classic) -> marca repo + delete_repo + workflow" -ForegroundColor Yellow
  pause; exit 1
}
Write-Host ""
Write-Host "[2/4] A apagar Spoon-Knife..." -ForegroundColor Gray
try {
  Invoke-RestMethod -Uri "https://api.github.com/repos/robertoMF170/Spoon-Knife" -Headers $headers -Method Delete | Out-Null
  Write-Host "[OK] Spoon-Knife apagado (204)" -ForegroundColor Green
} catch {
  $code = 0
  try { $code = $_.Exception.Response.StatusCode.Value__ } catch {}
  if ($code -eq 404) { Write-Host "[OK] Spoon-Knife ja nao existia (404)" -ForegroundColor Green }
  elseif ($code -eq 403) { Write-Host "[ERRO] 403 Sem permissao delete_repo - recria o token classic com delete_repo marcado" -ForegroundColor Red }
  else { Write-Host "[AVISO] Delete falhou: $($_.Exception.Message) (code $code)" -ForegroundColor Yellow; if($_.ErrorDetails.Message){ Write-Host $_.ErrorDetails.Message } }
}
Write-Host ""
Write-Host "[3/4] A criar 13 repos..." -ForegroundColor Gray
$repos = @(
  @{name="srrobs-skin-trader-pro"; desc="Skin Trader Pro - EV trade-ups (Steam + CSFloat + Skinport + DMarket) - Flask"},
  @{name="steamgamessnipe-free-games"; desc="Free Games Sniper - Bot Discord -100% (Node 20 + discord.js)"},
  @{name="robos-farmer-cs2"; desc="Robs Farmer - CS2 CustomTkinter + Arduino Leonardo + vgamepad"},
  @{name="okx-supertrend-scanner"; desc="OKX SuperTrend AI Scanner - LuxAlgo K-means + Fibonacci (FastAPI)"},
  @{name="pinecode-confluence-engine"; desc="Confluence Engine - RebelsFunding (Pine + MQL5 + Tampermonkey)"},
  @{name="kronos-klines-ai"; desc="Kronos - K-Lines Foundation Model (NeoQuasar) - wrapper SrRobs"},
  @{name="fimathe-cycle-pcm"; desc="Fimathe Cycle + PCM - Canal + Zona Neutra + PCM (Pine v6)"},
  @{name="pokemmo-srrobs"; desc="PokeMMO SrRobs - Controller + OCR + SQLite (Alpha e Beta)"},
  @{name="bets-converter-paqbet"; desc="Bets Converter - Paqbet booking code converter (Flask + BS4)"},
  @{name="mt2robs-lite"; desc="MT2Robs Lite - Energy Bot + Locator (Gameforge, eXLib.mix)"},
  @{name="tbh-toolkit-5contas"; desc="TaskBarHero Toolkit - 5 contas via Sandboxie, baus, builds, MSS"},
  @{name="csgo500-sessao-500-lab"; desc="Laboratorio Sessao 500 - CSGO500 (Monte Carlo 10k + HUD + OpenCV)"},
  @{name="srrobs-portfolio"; desc="SrRobs Portfolio - ewan-kerboas inspired, preto/branco/vermelho"}
)
foreach ($r in $repos) {
  $body = @{name=$r.name; description=$r.desc; private=$false; auto_init=$true} | ConvertTo-Json
  try {
    $null = Invoke-RestMethod -Uri "https://api.github.com/user/repos" -Headers $headers -Method Post -Body $body
    Write-Host "  + $($r.name) - criado (201)" -ForegroundColor Green
  } catch {
    $code = 0
    try { $code = $_.Exception.Response.StatusCode.Value__ } catch {}
    $msg = $_.ErrorDetails.Message
    if ($code -eq 422) { Write-Host "  = $($r.name) - ja existe (422) ok" -ForegroundColor Yellow }
    elseif ($code -eq 403) { Write-Host "  [ERRO] $($r.name) - 403 sem permissao (token sem repo scope)" -ForegroundColor Red; Write-Host "       $msg" -ForegroundColor Red }
    else { Write-Host "  [ERRO] $($r.name) - $code : $msg" -ForegroundColor Red }
  }
}
Write-Host ""
Write-Host "[4/4] Repos atuais em robertoMF170:" -ForegroundColor Gray
try {
  $all = Invoke-RestMethod -Uri "https://api.github.com/user/repos?per_page=100&visibility=all&affiliation=owner" -Headers $headers -Method Get
  $all | ForEach-Object { $vis = if ($_.private) { 'private' } else { 'public' }; Write-Host "  - $($_.name)  ($vis) - $($_.html_url)" }
  Write-Host ""
  Write-Host "Total: $($all.Count) repos" -ForegroundColor Cyan
} catch {
  Write-Host "[AVISO] Falha ao listar: $($_.Exception.Message)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " DONE - 201=criado, 422=ja existia, 403=token sem permissao" -ForegroundColor Cyan
Write-Host " Proximo: corre 2-push-all-12.bat para subir codigo de D:\" -ForegroundColor Cyan
Write-Host " Depois apaga o token em github.com/settings/tokens" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
pause
