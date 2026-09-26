@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================================
echo  SrRobs — 2/2 Push 12 projetos de D:\ para GitHub
echo  Requer git instalado + token Classic no credential helper
echo ============================================================
echo.

REM --- Pede token para push via URL ---
set "TOKEN="
set /p TOKEN="Cola o ghp_... para push (ou deixa vazio se ja fizeste gh auth): "

set USER=robertoMF170
set "SETUP_DIR=%~dp0"

REM --- Mapa pasta local -> repo remoto ---
REM Ajusta se a tua pasta em D:\ tiver nome ligeiramente diferente
call :push_one "D:\cs2snipre"            "srrobs-skin-trader-pro"
call :push_one "D:\steamgamessnipe"        "steamgamessnipe-free-games"
call :push_one "D:\CS2BotImprover"         "robos-farmer-cs2"
call :push_one "D:\okx"                    "okx-supertrend-scanner"
call :push_one "D:\pinecode"               "pinecode-confluence-engine"
call :push_one "D:\kronos"                 "kronos-klines-ai"
call :push_one "D:\FIMAYHE PCM"            "fimathe-cycle-pcm"
call :push_one "D:\pokemmo"                "pokemmo-srrobs"
call :push_one "D:\coversorbets"           "bets-converter-paqbet"
call :push_one "D:\metin2\MT2Robs-Lite"    "mt2robs-lite"
call :push_one "D:\tbh 2"                  "tbh-toolkit-5contas"
call :push_one "D:\csgo500 vamos ser ricos com a sorte" "csgo500-sessao-500-lab"

echo.
echo --- Portfolio (este site, pasta atual) ---
call :push_portfolio

echo.
echo ============================================================
echo  FIM — verifica em https://github.com/robertoMF170
echo  Depois apaga o token em github.com/settings/tokens
echo  E limpa credencial: cmdkey /delete:git:https://github.com
echo ============================================================
pause
exit /b 0

:push_one
set "SRC=%~1"
set "REPO=%~2"
echo.
echo === %REPO% ^<^<= %SRC%
if not exist "%SRC%" (
  echo [AVISO] Pasta nao encontrada: %SRC% -- a saltar.
  exit /b 0
)
pushd "%SRC%"
REM Decide URL com ou sem token
if "%TOKEN%"=="" (
  set "URL=https://github.com/%USER%/%REPO%.git"
) else (
  set "URL=https://%TOKEN%@github.com/%USER%/%REPO%.git"
)
REM Init se nao for repo ainda
if not exist ".git" (
  git init
  git branch -M main
) else (
  git branch -M main 2>nul
)
REM Injeta README detalhado se a pasta nao tiver um
if not exist "README.md" (
  if "%REPO%"=="srrobs-skin-trader-pro" if exist "%SETUP_DIR%readmes\01-srrobs-skin-trader-pro-README.md" copy /Y "%SETUP_DIR%readmes\01-srrobs-skin-trader-pro-README.md" "README.md" >nul
  if "%REPO%"=="steamgamessnipe-free-games" if exist "%SETUP_DIR%readmes\02-steamgamessnipe-free-games-README.md" copy /Y "%SETUP_DIR%readmes\02-steamgamessnipe-free-games-README.md" "README.md" >nul
  if "%REPO%"=="robos-farmer-cs2" if exist "%SETUP_DIR%readmes\03-robos-farmer-cs2-README.md" copy /Y "%SETUP_DIR%readmes\03-robos-farmer-cs2-README.md" "README.md" >nul
  if "%REPO%"=="okx-supertrend-scanner" if exist "%SETUP_DIR%readmes\04-okx-supertrend-scanner-README.md" copy /Y "%SETUP_DIR%readmes\04-okx-supertrend-scanner-README.md" "README.md" >nul
  if "%REPO%"=="pinecode-confluence-engine" if exist "%SETUP_DIR%readmes\05-pinecode-confluence-engine-README.md" copy /Y "%SETUP_DIR%readmes\05-pinecode-confluence-engine-README.md" "README.md" >nul
  if "%REPO%"=="kronos-klines-ai" if exist "%SETUP_DIR%readmes\06-kronos-klines-ai-README.md" copy /Y "%SETUP_DIR%readmes\06-kronos-klines-ai-README.md" "README.md" >nul
  if "%REPO%"=="fimathe-cycle-pcm" if exist "%SETUP_DIR%readmes\07-fimathe-cycle-pcm-README.md" copy /Y "%SETUP_DIR%readmes\07-fimathe-cycle-pcm-README.md" "README.md" >nul
  if "%REPO%"=="pokemmo-srrobs" if exist "%SETUP_DIR%readmes\08-pokemmo-srrobs-README.md" copy /Y "%SETUP_DIR%readmes\08-pokemmo-srrobs-README.md" "README.md" >nul
  if "%REPO%"=="bets-converter-paqbet" if exist "%SETUP_DIR%readmes\09-bets-converter-paqbet-README.md" copy /Y "%SETUP_DIR%readmes\09-bets-converter-paqbet-README.md" "README.md" >nul
  if "%REPO%"=="mt2robs-lite" if exist "%SETUP_DIR%readmes\10-mt2robs-lite-README.md" copy /Y "%SETUP_DIR%readmes\10-mt2robs-lite-README.md" "README.md" >nul
  if "%REPO%"=="tbh-toolkit-5contas" if exist "%SETUP_DIR%readmes\11-tbh-toolkit-5contas-README.md" copy /Y "%SETUP_DIR%readmes\11-tbh-toolkit-5contas-README.md" "README.md" >nul
  if "%REPO%"=="csgo500-sessao-500-lab" if exist "%SETUP_DIR%readmes\12-csgo500-sessao-500-lab-README.md" copy /Y "%SETUP_DIR%readmes\12-csgo500-sessao-500-lab-README.md" "README.md" >nul
  if exist "README.md" echo [README] Injetado README detalhado para %REPO%
)
REM Garante .gitignore sensato se nao existir
if not exist ".gitignore" (
  echo __pycache__/>> .gitignore
  echo .venv/>> .gitignore
  echo venv/>> .gitignore
  echo node_modules/>> .gitignore
  echo .env>> .gitignore
  echo *.log>> .gitignore
  echo events.db>> .gitignore
  echo debug.txt>> .gitignore
  echo shots/>> .gitignore
  echo baus_cache.json>> .gitignore
)
git remote remove origin 2>nul
git remote add origin "%URL%"
REM Substitui URL com token por URL limpa apos push para nao ficar gravado
git add -A
git commit -m "chore: initial import — %REPO% (SrRobs)" 2>nul
if errorlevel 1 echo [INFO] Nada novo para commit ou ja committed.
echo [PUSH] origin main ...
git push -u origin main --force
if errorlevel 1 (
  echo [ERRO] Push falhou para %REPO%. Verifica token / rede.
) else (
  echo [OK] %REPO% enviado.
  REM Limpa token da URL remota
  git remote set-url origin https://github.com/%USER%/%REPO%.git
)
popd
exit /b 0

:push_portfolio
REM Este repo = pasta onde esta este .bat + site (assumindo que copiaste)
set "REPO=srrobs-portfolio"
set "SRC=%~dp0.."
if not exist "%SRC%\index.html" set "SRC=%CD%"
echo === %REPO% ^<^<= %SRC%
pushd "%SRC%"
if "%TOKEN%"=="" ( set "URL=https://github.com/%USER%/%REPO%.git" ) else ( set "URL=https://%TOKEN%@github.com/%USER%/%REPO%.git" )
if not exist ".git" ( git init & git branch -M main ) else ( git branch -M main 2>nul )
if not exist "README.md" if exist "%SETUP_DIR%readmes\13-srrobs-portfolio-README.md" copy /Y "%SETUP_DIR%readmes\13-srrobs-portfolio-README.md" "README.md" >nul
if not exist ".gitignore" ( echo node_modules/>> .gitignore & echo .env>> .gitignore )
git remote remove origin 2>nul
git remote add origin "%URL%"
git add index.html style.css app.js README.md 2>nul
if exist "github-setup" git add github-setup 2>nul
if exist ".gitignore" git add .gitignore 2>nul
git commit -m "feat: SrRobs portfolio — ewan-kerboas inspired (preto/branco/vermelho)" 2>nul
if errorlevel 1 echo [INFO] Nada novo para commit portfolio.
git push -u origin main --force
git remote set-url origin https://github.com/%USER%/%REPO%.git 2>nul
popd
exit /b 0
