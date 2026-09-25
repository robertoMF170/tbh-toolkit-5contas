@echo off
chcp 65001 >nul
title TUDO SYNC (1 vez) - Builds + Baus + Inventario + UPAR JA
cd /d "%~dp0"
echo === 1/2 Gerando builds PERFEITAS sincronizadas com o SAVE (arvore/runa/UPAR JA) ===
python -X utf8 -u tbh_site.py
echo.
echo === 2/2 Atualizando baus + abas UPAR JA + inventario.html ===
python -X utf8 -u tbh_baus.py --abrir
echo.
echo Feito. Dashboard: minhas_builds.html e inventario.html atualizados.
echo Para FARM CONTINUO (ciclo estavel 15 min) usa: atualizar_baus_agora.bat  (ou abrir_minhas_builds.bat)
pause
