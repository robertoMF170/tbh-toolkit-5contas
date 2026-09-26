# SrRobs — 6) Reescrever historico do TBH (remove saves/contas de TODOS os commits)
#
# PORQUE: o passo 5 so limpa o HEAD. Os .es3/baus.json/contas continuam em commits
# antigos e acessiveis por SHA. Isto reescreve o historico como se nunca tivessem
# existido. O repo fica pequeno e sem dados pessoais.
#
# REQUISITO: git-filter-repo  ->  pip install git-filter-repo
#            (o script instala automaticamente se faltar)
#
# ATENCAO: reescreve o repo INTEIRO no GitHub (main). Local D:\ nao e tocado.
#          Quem tiver clones antigos tem de re-clonar.
#
# Uso: powershell -ExecutionPolicy Bypass -File .\6-rewrite-history.ps1

$ErrorActionPreference = "Continue"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SrRobs - Reescrever historico git do TBH" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$token = Read-Host "Cola o ghp_... (classic, scope repo) e pressiona ENTER"
$token = $token.Trim()
if (-not $token) { Write-Host "[ERRO] Token vazio" -ForegroundColor Red; pause; exit 1 }

$user = "robertoMF170"
$repo = "tbh-toolkit-5contas"

# --- 0) git identity sem email pessoal ---
git config --global user.name  "SrRobs" 2>$null
git config --global user.email "SrRobsParecias@proton.me" 2>$null

# --- 1) garantir git-filter-repo ---
$hasFilterRepo = $false
try { git filter-repo --version 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $hasFilterRepo = $true } } catch {}
if (-not $hasFilterRepo) {
  Write-Host "[1/5] git-filter-repo nao encontrado - a instalar via pip..." -ForegroundColor Gray
  pip install git-filter-repo 2>&1 | Out-Null
  try { git filter-repo --version 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $hasFilterRepo = $true } } catch {}
}
if (-not $hasFilterRepo) {
  Write-Host "[ERRO] nao consegui instalar git-filter-repo." -ForegroundColor Red
  Write-Host "       Instala Python + 'pip install git-filter-repo' e volta a correr." -ForegroundColor Yellow
  pause; exit 1
}
Write-Host "[1/5] git-filter-repo OK" -ForegroundColor Green

# --- 2) clone fresco (mirror nao: filter-repo funciona em clone normal) ---
$tmpRoot = Join-Path $env:TEMP "srrobs-rewrite"
if (Test-Path $tmpRoot) { Remove-Item $tmpRoot -Recurse -Force }
New-Item -ItemType Directory -Path $tmpRoot | Out-Null
$work = Join-Path $tmpRoot $repo
Write-Host "[2/5] clone fresco de $user/$repo ..." -ForegroundColor Gray
git clone "https://$token@github.com/$user/$repo.git" $work 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] clone falhou" -ForegroundColor Red; pause; exit 1 }

# --- 3) paths a apagar do historico inteiro ---
$paths = @(
  "baus.json", "baus_historico.json", "baus_cache.json",
  "baus_para_importar",
  "abrir_conta1.bat", "abrir_conta2.bat", "abrir_conta3.bat", "abrir_conta4.bat", "abrir_conta5.bat",
  "abrir_todas_contas.bat", "abrir_minhas_builds.bat",
  "Sandboxie_backup.ini", "Sandboxie_utf8.ini",
  "abrir_steam.py.estado.txt",
  "alertas_dedup.json", "analysis_result.json",
  "game_manifest.acf", "game_version.txt",
  "captura_0_pid5224.png", "captura_1_pid27172.png", "captura_32772.png",
  "ecra_completo.png", "ecra_completo2.png", "ecra_completo3.png"
)

Push-Location $work
try {
  # --- 4) reescrever ---
  Write-Host "[3/5] reescrever historico ($($paths.Count) paths)..." -ForegroundColor Gray
  $pathArgs = @("--invert-paths")
  foreach ($p in $paths) { $pathArgs += "--path"; $pathArgs += $p }
  git filter-repo --force @pathArgs
  if ($LASTEXITCODE -ne 0) { Write-Host "[ERRO] filter-repo falhou" -ForegroundColor Red; pause; exit 1 }

  # filter-repo remove o remote por seguranca - repor com token para push
  git remote add origin "https://$token@github.com/$user/$repo.git" 2>$null | Out-Null

  # commit extra: .gitignore reforçado para estes ficheiros nunca mais voltarem
  $gi = ".gitignore"
  $extra = @(
    "", "# === SrRobs - dados pessoais: nunca commitar ===",
    "baus.json", "baus_historico.json", "baus_cache.json", "*.es3",
    "abrir_conta*.bat", "Sandboxie_*.ini", "*.estado.txt",
    "alertas_dedup.json", "analysis_result.json", "game_manifest.acf",
    "captura_*.png", "ecra_completo*.png"
  ) -join "`n"
  if (Test-Path $gi) { Add-Content $gi $extra -Encoding utf8 } else { $extra | Out-File $gi -Encoding utf8 }
  git add .gitignore
  $st = git status --porcelain
  if ($st) { git commit -m "chore: .gitignore bloqueia saves/contas/configs pessoais" | Out-Null }

  # --- 5) push forcado ---
  Write-Host "[4/5] push --force para $user/$repo ..." -ForegroundColor Gray
  git push origin main --force 2>&1 | Out-Host
  if ($LASTEXITCODE -eq 0) {
    Write-Host "[5/5] OK - historico reescrito." -ForegroundColor Green
  } else {
    Write-Host "[ERRO] push falhou - verifica token/permissao" -ForegroundColor Red
    pause; exit 1
  }
} finally { Pop-Location }

# limpar pasta temporaria com os clones
Remove-Item $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
Set-Clipboard -Value "" 2>$null

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " FEITO. Os saves/contas deixaram de existir no GitHub." -ForegroundColor Green
Write-Host "" -ForegroundColor Cyan
Write-Host " AINDA POR FAZER:" -ForegroundColor Yellow
Write-Host " 1. GC do lado GitHub (pode levar dias, automatizado)." -ForegroundColor Yellow
Write-Host "    Os SHAs antigos ficam orfaos ate la. Nada esta 'escondido'," -ForegroundColor Yellow
Write-Host "    mas sem SHA ninguem chega la pelo site normal." -ForegroundColor Yellow
Write-Host " 2. Contacta support@github.com com o link do repo e pede" -ForegroundColor Yellow
Write-Host "    'run a garbage collection on this repository' - eles" -ForegroundColor Yellow
Write-Host "    correm-na na hora para casos de dados pessoais." -ForegroundColor Yellow
Write-Host " 3. Se os saves .es3 eram valiosos: estao intactos no teu D:\" -ForegroundColor Yellow
Write-Host " 4. Apaga o token em github.com/settings/tokens" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
pause
