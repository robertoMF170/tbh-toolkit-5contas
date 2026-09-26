@echo off
chcp 65001 >nul
title 8 - Atualizar Tudo (12 repos + site SrRobs)

echo ============================================================
echo  SrRobs - 8 - ATUALIZAR TUDO (12 repos + site/portfolio)
echo  [1] Analisar tudo   [2] Novo push   [3] Auto (5 em 5 min)
echo ============================================================
echo.

set "SETUP_DIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SETUP_DIR%8-atualizar-tudo.ps1"

echo.
echo ============================================================
echo  FIM - depois de um push com token, revoga:
echo  github.com/settings/tokens
echo  cmdkey /delete:git:https://github.com
echo ============================================================
pause
exit /b 0
