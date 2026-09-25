@echo off
chcp 65001 >nul
title FARM ESTAVEL 15 min - 5 contas [builds+baus+UPAR JA+inventario]
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================================
echo  FARM ESTAVEL - CICLO 15 MIN (5 contas, TUDO novo)
echo  Igual ao antigo (15 min) mas com todas as funcoes novas:
echo   - Builds PERFEITAS sincronizadas com o SAVE (5 builds)
echo     arvore SKILLS verde/feito laranja/parcial dourado
echo     mapa RUNAS verde/comprada laranja/alcancada
echo   - Baus vendaveis + historico + inventario (5 contas)
echo   - Aba UPAR JA real por conta vs alvo da build
echo  Este bat NAO fecha sozinho: se der erro, espera 30s e
echo  recomeca. Para parar, fecha a janela ou Ctrl+C.
echo ============================================================
echo  Log: baus_monitor.log  (abre com bloco de notas se quiseres)
echo  Tempo entre pontos no grafico: minimo 5 min (ja logado)
echo  Se a janela fechar, o grafico para - deixa-a ABERTA.
echo ============================================================
echo.

REM ciclo estavel = monitor python com builds a cada 15 min + baus leves a cada 2 min
REM O python ja trata de TUDO: regenera builds, atualiza baus/UPAR JA/inventario,
REM mede no site quando precisa, e nunca sai sozinho (retry 30s).
echo A iniciar o ciclo... (se falhar, recomeca sozinho em 30s)
echo.

:loop
python -X utf8 -u tbh_baus.py --monitor 15
echo.
echo [AVISO] O monitor saiu (codigo %errorlevel%). A reiniciar em 30s...
echo Se quiseres parar de vez, fecha esta janela agora (Ctrl+C ja nao basta
echo se o python crashar - fecha a janela).
timeout /t 30 /nobreak
if errorlevel 1 goto fim
echo A reiniciar o ciclo...
goto loop

:fim
echo Farm parado.
pause
