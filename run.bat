@echo off
chcp 65001 >nul
title TBH — RUN (site completo + extras locais)
cd /d "%~dp0"
setlocal

REM --- Modulos opcionais: a versao publica so inclui o gerador do site ---
set TEM_STEAM=
if exist "%~dp0src\abrir_steam.py" set TEM_STEAM=1
set TEM_BAUS=
if exist "%~dp0src\tbh_baus.py" set TEM_BAUS=1

if "%~1"=="--help" goto ajuda
if "%~1"=="-h" goto ajuda
if "%~1"=="/?" goto ajuda
goto inicio

:ajuda
echo Uso: run.bat [--forcar]
echo   sem args  - modo normal: gera o site completo e (se existirem os
echo               modulos locais) verifica sandboxes e inicia o ciclo 15 min
echo   --forcar  - forca arranque de TODAS as sandboxes mesmo que parecam
echo               a correr (so se src\abrir_steam.py existir)
echo   run.bat e o UNICO arranque - legados em scripts/ chamam este
exit /b 0

:inicio
echo ============================================================
echo  TBH 2 — RUN  (unico arranque - usa SEMPRE este)
echo  Fecha esta janela ou Ctrl+C para parar
echo ============================================================
echo  Estrutura: run.bat + minhas_builds.html + inventario.html na RAIZ
echo             src/ (codigo), assets/ (icons), config/ (baus/builds), data/tbhdata, var/ (cache)
echo  O que este RUN faz (tudo em 1):
echo   1) gera site completo: builds + baus + farm + mapa + UPAR JA
echo      - farm em baixo horizontal (texto todo visivel)
echo      - filtros: Equilibrio / Mais caros / Mais facil vender / Mais facil drop
echo      - ver mapa estilo jogo: bolas alinhadas, boss vermelho, bola pintada onde farmar
echo   2) se existirem os modulos locais: sandboxes + ciclo farm 15 min
echo      - modulos ausentes sao saltados automaticamente (versao publica)
echo ============================================================
echo.

set FORCAR=
if /I "%~1"=="--forcar" set FORCAR=--forcar
if /I "%~1"=="--forçar" set FORCAR=--forcar
if /I "%~1"=="--force" set FORCAR=--forcar

if not defined TEM_STEAM goto sem_steam

echo [1/4] Estado das sandboxes (SbieSvc + logins)...
python -X utf8 src\abrir_steam.py --estado
echo.

REM --- Prompt Y/S para login (farm fica desligado por defeito) ---
if defined FORCAR goto forcar_login

echo Quer fazer login das contas?
choice /C YS /N /T 15 /D S /M "  [Y]es = abrir sandboxes   [S]altar = saltar (padrao S em 15s): "
if errorlevel 2 goto skip_login
if errorlevel 1 goto do_login

:do_login
echo.
echo [2/4] A abrir sandboxes em falta (se ja ativa, salta sozinha)...
echo       Se alguma ficar AMBIGUA (pid mudou / login nao visto) vai perguntar [S]altar / [L]ogar
python -X utf8 src\abrir_steam.py --todas
goto pos_login

:forcar_login
echo [2/4] A abrir TODAS as sandboxes (FORCAR — ignora deteccao)...
python -X utf8 src\abrir_steam.py --todas --forcar
goto pos_login

:skip_login
echo.
echo [2/4] Login das contas SALTADO (S) — sem abrir sandboxes.
echo       Sandboxes deixadas como estao — o ciclo 15min continua a ler saves locais na mesma.
goto pos_login

:sem_steam
echo [1/4] src\abrir_steam.py ausente (versao publica) — sandboxes SALTADAS.
echo [2/4] Login das contas SALTADO — modulo local ausente.
echo.

:pos_login
if defined TEM_STEAM echo       Sandboxes prontas (ativas saltadas / saltadas por S / lancadas).
echo.

echo [3/4] A gerar minhas_builds.html (builds perfeitas sincronizadas com SAVE)...
python -X utf8 -u src\tbh_site.py --sem-abrir
if errorlevel 1 (
  echo  ERRO ao gerar builds - nova tentativa em 5s...
  timeout /t 5 /nobreak >nul
  python -X utf8 -u src\tbh_site.py --sem-abrir
)
if errorlevel 1 (
  echo  ERRO: src\tbh_site.py falhou duas vezes - ve o erro acima.
  echo  O ciclo vai tentar na mesma, mas corrige o erro primeiro.
) else (
  echo  OK builds geradas.
)
echo.

if not defined TEM_BAUS goto sem_baus
echo       A atualizar baus + inventario + UPAR JA (sem abrir browser)...
python -X utf8 -u src\tbh_baus.py --atualizar
if errorlevel 1 (
  echo  aviso: baus --atualizar falhou - o monitor vai retentar no ciclo
) else (
  echo  OK baus/inventario/UPAR JA atualizados.
)
echo.

:sem_baus
if exist "%~dp0minhas_builds.html" (
  echo  A abrir dashboard no browser...
  start "" "%~dp0minhas_builds.html"
) else (
  echo  ERRO: minhas_builds.html nao foi gerada! Verifica o erro acima.
)
echo.

if not defined TEM_BAUS goto sem_monitor
echo [4/4] A iniciar CICLO ESTAVEL 15 min
echo       leve a cada 2 min (saves locais - baus/progresso/UPAR JA/inventario)
echo       completo a cada 15 min (regenera builds SKILLS/RUNAS sincronizadas)
echo       log: var\baus_monitor.log  - deixa esta janela ABERTA durante o farm
echo       Para parar de vez: fecha esta janela
echo ============================================================
echo.

:loop
python -X utf8 -u src\tbh_baus.py --monitor 15
echo.
echo [AVISO] Monitor saiu (codigo %errorlevel%). Reinicia em 30s...
echo Fecha esta janela agora se queres parar de vez.
timeout /t 30 /nobreak
if errorlevel 1 goto fim
echo A reiniciar ciclo...
goto loop

:sem_monitor
echo [4/4] Modulo de baus/farm ausente (versao publica) — monitor SALTADO.
echo       O site foi gerado e aberto no browser. Podes fechar esta janela.
echo ============================================================

:fim
echo Run terminado.
pause
