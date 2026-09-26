@echo off
REM SrRobs — 1/2 Criar 13 repos + apagar Spoon-Knife
REM CORRE PELO CMD, nao por duplo clique: Win+R > cmd > cd pasta > 1-criar-repos.bat
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================================
echo  SrRobs -- 1/2 Criar 13 repos + apagar Spoon-Knife
echo  Precisas de um token Classic (ghp_...) com repo + delete_repo
echo  Nao abras por duplo clique -- abre o CMD primeiro!
echo ============================================================
echo.
where curl >nul 2>&1
if errorlevel 1 (
  echo [ERRO] curl nao encontrado. Instala Git for Windows:
  echo   https://git-scm.com/download/win
  echo e tenta de novo pelo CMD.
  pause
  exit /b 1
)
echo [OK] curl encontrado
where powershell >nul 2>&1
if errorlevel 1 echo [AVISO] powershell nao encontrado -- listagem final sera simples

echo.
set "TOKEN="
set /p TOKEN="Cola o teu ghp_... e pressiona ENTER: "
if "%TOKEN%"=="" (
  echo [ERRO] Token vazio. Cola o ghp_...
  pause
  exit /b 1
)
if "%TOKEN:~0,4%" NEQ "ghp_" (
  echo [AVISO] Token nao comeca com ghp_ -- e Classic mesmo? Vou tentar na mesma...
)

echo.
echo [1/4] A verificar autenticacao...
curl -s -H "Authorization: Bearer %TOKEN%" -H "Accept: application/vnd.github+json" https://api.github.com/user > "%TEMP%\srrobs_user.json"
type "%TEMP%\srrobs_user.json"
echo.
findstr /C:"robertoMF170" "%TEMP%\srrobs_user.json" >nul
if errorlevel 1 (
  echo.
  echo [ERRO] Token invalido, expirado ou sem acesso a robertoMF170.
  echo Verifica em github.com/settings/tokens se o token existe e tem repo+delete_repo.
  pause
  exit /b 1
)
echo [OK] Autenticado como robertoMF170

echo.
echo [2/4] A apagar Spoon-Knife se existir...
curl -s -X DELETE -H "Authorization: Bearer %TOKEN%" -H "Accept: application/vnd.github+json" https://api.github.com/repos/robertoMF170/Spoon-Knife -w " HTTP:%%{http_code}\n" -o "%TEMP%\srrobs_del.json"
echo Resposta delete:
type "%TEMP%\srrobs_del.json"
echo 204=apagado, 404=ja nao existia (ok), 403=sem permissao delete_repo

echo.
echo [3/4] A criar 13 repos novos...
echo.

call :create_repo "srrobs-skin-trader-pro" "Skin Trader Pro -- EV trade-ups (Steam + CSFloat + Skinport + DMarket) -- Flask"
call :create_repo "steamgamessnipe-free-games" "Free Games Sniper -- Bot Discord -100%% (Node 20 + discord.js)"
call :create_repo "robos-farmer-cs2" "Robs Farmer -- CS2 CustomTkinter + Arduino Leonardo + vgamepad"
call :create_repo "okx-supertrend-scanner" "OKX SuperTrend AI Scanner -- LuxAlgo K-means + Fibonacci (FastAPI)"
call :create_repo "pinecode-confluence-engine" "Confluence Engine -- RebelsFunding (Pine + MQL5 + Tampermonkey)"
call :create_repo "kronos-klines-ai" "Kronos -- K-Lines Foundation Model (NeoQuasar) -- wrapper SrRobs"
call :create_repo "fimathe-cycle-pcm" "Fimathe Cycle + PCM -- Canal + Zona Neutra + PCM (Pine v6)"
call :create_repo "pokemmo-srrobs" "PokeMMO SrRobs -- Controller + OCR + SQLite (Alpha e Beta)"
call :create_repo "bets-converter-paqbet" "Bets Converter -- Paqbet booking code converter (Flask + BS4)"
call :create_repo "mt2robs-lite" "MT2Robs Lite -- Energy Bot + Locator (Gameforge, eXLib.mix)"
call :create_repo "tbh-toolkit-5contas" "TaskBarHero Toolkit -- 5 contas via Sandboxie, baus, builds, MSS"
call :create_repo "csgo500-sessao-500-lab" "Laboratorio Sessao 500 -- CSGO500 (Monte Carlo 10k + HUD + OpenCV)"
call :create_repo "srrobs-portfolio" "SrRobs Portfolio -- ewan-kerboas inspired, preto/branco/vermelho"

echo.
echo [4/4] Repos atuais em robertoMF170:
curl -s -H "Authorization: Bearer %TOKEN%" -H "Accept: application/vnd.github+json" "https://api.github.com/user/repos?per_page=100&visibility=all&affiliation=owner" > "%TEMP%\srrobs_repos.json"
powershell -Command "(Get-Content '%TEMP%\srrobs_repos.json' | ConvertFrom-Json | Select-Object -ExpandProperty name)" 2>nul
if errorlevel 1 (
  echo (fallback sem powershell)
  findstr "\"name\":" "%TEMP%\srrobs_repos.json"
)

echo.
echo ============================================================
echo  DONE -- 201=criado, 422=ja existia (ok). 403=sem permissao
echo  Logs em %%TEMP%%\srrobs_*.json
echo  Proximo: corre 2-push-all-12.bat
echo  Depois apaga o token em github.com/settings/tokens
echo ============================================================
pause
exit /b 0

:create_repo
set "RNAME=%~1"
set "RDESC=%~2"
echo  - %RNAME% ...
curl -s -w " HTTP_CODE:%%{http_code} " -o "%TEMP%\srrobs_create_%RNAME%.json" -X POST -H "Authorization: Bearer %TOKEN%" -H "Accept: application/vnd.github+json" -d "{\"name\":\"%RNAME%\",\"description\":\"%RDESC%\",\"private\":false,\"auto_init\":true}" https://api.github.com/user/repos
type "%TEMP%\srrobs_create_%RNAME%.json" | findstr /C:"message" >nul
if not errorlevel 1 type "%TEMP%\srrobs_create_%RNAME%.json"
echo.
exit /b 0
