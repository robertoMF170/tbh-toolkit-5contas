@echo off
chcp 65001 >nul
title Monitor Baus + UPAR JA (legado - usa abrir_minhas_builds.bat para ciclo completo)
cd /d "%~dp0"
echo Este e o monitor LEGADO (so baus, ciclo 2 min rapido + 15 min medicao).
echo Para o FARM COMPLETO em ciclo (builds+baus+inventario+UPAR JA + skills/runas sincronizadas)
echo usa: abrir_minhas_builds.bat  (recomendado - ciclo 2 min de TUDO)
echo.
echo A continuar com o monitor legado em 4 segundos... Ctrl+C para cancelar.
timeout /t 4 /nobreak >nul
python -u tbh_baus.py --monitor 15
pause
