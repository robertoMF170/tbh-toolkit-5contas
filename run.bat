@echo off
chcp 65001 >nul
title TBH — RUN + ALERTAS FARM (2s)
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
echo   sem args  - modo normal: confirma os saves vs Steam Cloud, gera o site
echo               e (se existirem os modulos locais) faz login e inicia o ciclo
echo   --forcar  - forca arranque de TODAS as sandboxes mesmo que parecam
echo               a correr (so se src\abrir_steam.py existir)
echo   run.bat e o UNICO arranque - inclui alertas de drop em tempo real
exit /b 0

:inicio
echo ============================================================
echo  TBH 2 — RUN  (unico arranque - usa SEMPRE este)
echo  Fecha esta janela ou Ctrl+C para parar
echo ============================================================
echo  Estrutura: run.bat + minhas_builds.html + inventario.html na RAIZ
echo             src/ (codigo), assets/ (icons), config/ (baus/builds), data/tbhdata, var/ (cache)
echo  O que este RUN faz (tudo em 1):
echo   1) confirma os saves vs Steam Cloud ANTES de arrancar contas
echo      - backup automatico + nao deixa sobrescrever a cloud com save velho
echo   2) gera site completo: builds + baus + farm + mapa + UPAR JA
echo      - ver mapa estilo jogo: bolas alinhadas, boss vermelho, bola pintada onde farmar
echo   3) alertas de item a cada 2 segundos + popup quando houver drop
echo   4) se existirem os modulos locais: sandboxes + ciclo baus 15 min
echo ============================================================
echo.

set FORCAR=
if /I "%~1"=="--forcar" set FORCAR=--forcar
if /I "%~1"=="--forçar" set FORCAR=--forcar
if /I "%~1"=="--force" set FORCAR=--forcar

if not defined TEM_STEAM goto sem_steam_1

echo [1/5] Estado das sandboxes (SbieSvc + logins)...
python -X utf8 src\abrir_steam.py --estado
echo.
goto sync

:sem_steam_1
echo [1/5] src\abrir_steam.py ausente (versao publica) — sandboxes SALTADAS.
echo.

:sync
if not exist src\tbh_sync.py goto sem_sync
echo [2/5] A confirmar saves vs Steam Cloud (anti-perda de dados)...
python -X utf8 src\tbh_sync.py --pre
if errorlevel 3 goto fim
if errorlevel 2 goto sync_erro
if errorlevel 1 (
  echo  AVISO: houve divergencias de saves - decisao tomada acima.
)
echo.
goto login_pergunta

:sync_erro
echo.
echo        [ERRO] Ha contas SEM save utilizavel (ve acima) - arrancar agora
echo        pode sobrescrever a Steam Cloud e PERDER progresso!
choice /C SN /N /M "  [S]im = continuar mesmo assim   [N]ao = parar agora: "
if errorlevel 2 goto fim
echo.
goto login_pergunta

:sem_sync
echo [2/5] src\tbh_sync.py ausente — verificacao de saves SALTADA.
echo.

:login_pergunta
if not defined TEM_STEAM goto sem_steam_2

REM --- Prompt Y/S para login (farm fica desligado por defeito) ---
if defined FORCAR goto forcar_login

echo [3/5] Quer fazer login das contas?
choice /C YS /N /T 15 /D S /M "  [Y]es = abrir sandboxes   [S]altar = saltar (padrao S em 15s): "
if errorlevel 2 goto skip_login
if errorlevel 1 goto do_login

:do_login
echo.
echo [3/5] A abrir sandboxes em falta (se ja ativa, salta sozinha)...
echo       Se alguma ficar AMBIGUA (pid mudou / login nao visto) vai perguntar [S]altar / [L]ogar
python -X utf8 src\abrir_steam.py --todas --debug
if errorlevel 1 (
  echo  [ERRO] alguma conta nao abriu o jogo - detalhes em var\abrir_steam.log
)
goto pos_login

:forcar_login
echo [3/5] A abrir TODAS as sandboxes (FORCAR — ignora deteccao)...
python -X utf8 src\abrir_steam.py --todas --forcar --debug
if errorlevel 1 (
  echo  [ERRO] alguma conta nao abriu o jogo - detalhes em var\abrir_steam.log
)
goto pos_login

:skip_login
echo.
echo [3/5] Login das contas SALTADO (S) — sem abrir sandboxes.
echo       Sandboxes deixadas como estao — o ciclo 15min continua a ler saves locais na mesma.
goto pos_login

:sem_steam_2
echo [3/5] Login das contas SALTADO — modulo local ausente.

:pos_login
if defined TEM_STEAM echo       Sandboxes prontas (ativas saltadas / saltadas por S / lancadas).
echo.

echo [4/5] A gerar minhas_builds.html (builds perfeitas sincronizadas com SAVE)...
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
rem --- Alertas de farm: arrancam nesta janela e deixam heartbeat de saude ---
if not exist "%~dp0src\tbh_farm_alert.py" goto sem_farm_alert
:iniciar_farm_alert
echo [FARM] A arrancar vigia nesta janela; poll dos saves a cada 2 segundos.
echo       Clica Farmar. Titulo = item/conta; popup aparece no drop encontrado.
start "" /B python -X utf8 -u src\tbh_farm_alert.py --watch --interval 2
echo       A verificar arranque do processo...
timeout /t 2 /nobreak >nul
python -X utf8 src\tbh_farm_alert.py --status --interval 2
if errorlevel 4 goto farm_status_waiting
if errorlevel 3 goto farm_status_starting
if errorlevel 2 goto farm_status_warning
if errorlevel 1 goto farm_status_inactive
echo [FARM] OK — deixa esta janela aberta; o estado atualiza a cada 2 segundos.
goto farm_status_done
:farm_status_waiting
echo [FARM] ATIVO E A ESPERA DE ALVOS — clica Farmar na dashboard e confirma Abrir Python no browser.
goto farm_status_done
:farm_status_starting
echo [FARM] PROCESSO A ARRANCAR — verifica o estado com python -X utf8 src\tbh_farm_alert.py --status quando terminar.
goto farm_status_done
:farm_status_warning
echo [FARM] PROCESSO ATIVO, MAS COM ERROS — le a mensagem acima e confirma os saves/dados da conta.
goto farm_status_done
:farm_status_inactive
echo [FARM] VIGIA INATIVO. Verifica o Python e os caminhos dos saves em config\baus.json.
:farm_status_done
echo.
goto farm_alert_done

:sem_farm_alert
echo [FARM] Alertas indisponiveis: falta src\tbh_farm_alert.py.
echo.

:farm_alert_done
rem --- Servidor de visitas (estatisticas do painel #visitasPanel) ---
netstat -ano | findstr /C:":8765 " | findstr /C:"LISTENING" >nul 2>&1
if errorlevel 1 (
  if exist "%~dp0src\tbh_visitas.py" (
    echo  A arrancar servidor de visitas em http://localhost:8765 ...
    start "tbh-visitas" /min python -X utf8 "%~dp0src\tbh_visitas.py" --root "%~dp0" --db "%~dp0var\visitas.json"
    timeout /t 1 /nobreak >nul
  ) else (
    echo  aviso: src\tbh_visitas.py ausente - painel de visitas sem dados ao vivo.
  )
) else (
  echo  Servidor de visitas ja ativo na porta 8765 - nada a fazer.
)
echo.
if exist "%~dp0minhas_builds.html" (
  echo  A abrir dashboard no browser...
  start "" "%~dp0minhas_builds.html"
) else (
  echo  ERRO: minhas_builds.html nao foi gerada! Verifica o erro acima.
)
echo.

if not defined TEM_BAUS goto sem_monitor
echo [5/5] A iniciar CICLO ESTAVEL 15 min
echo       leve a cada 2 min (saves locais - baus/progresso/UPAR JA/inventario)
echo       completo a cada 15 min (regenera builds SKILLS/RUNAS sincronizadas)
echo       alertas de drop correm nesta janela em paralelo, a cada 2 segundos
echo       log: var\baus_monitor.log  - deixa esta janela ABERTA durante o farm
echo       Para parar de vez: fecha esta janela
echo ============================================================
echo.

:loop
python -X utf8 -u src\tbh_baus.py --monitor 15
echo.
echo [AVISO] Monitor saiu (codigo %errorlevel%). Reinicia em 30s...
echo Fecha esta janela agora se queres parar de vez.
rem espera a prova de cliques: 'timeout' devolve errorlevel 1 com um clique na
rem janela (QuickEdit) e fechava o run; 'ping' nao le o teclado/rato e nao falha
ping -n 31 127.0.0.1 >nul
echo A reiniciar ciclo...
goto loop

:sem_monitor
echo [5/5] Modulo local de baus ausente — ciclo de baus SALTADO.
echo       O alerta de farm (se disponivel) continua nesta janela em background.
echo       Fecha esta janela para parar o ciclo e os alertas.
echo ============================================================

:fim
echo Run terminado.
pause
