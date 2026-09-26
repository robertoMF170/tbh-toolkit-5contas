@echo off
chcp 65001 >nul
title SIEVE - seguir runs ate ao fim (retoma depois de crash)
cd /d "%~dp0\.."
echo ============================================================
echo  SIEVE - segue os runs guardados ate acabarem
echo ============================================================
echo  Usa os session_id guardados em sieve_runs.json. Se tiveres
echo  encerrado a meio, este comando retoma a poll SEM arrancar
echo  um run novo (cada run aceite gasta creditos).
echo ============================================================
echo.
python -X utf8 -u src/tbh_sieve.py --estado
echo.
python -X utf8 -u src/tbh_sieve.py --seguir
echo.
pause
