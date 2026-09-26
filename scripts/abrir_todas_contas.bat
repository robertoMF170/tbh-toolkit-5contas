@echo off

chcp 65001 >nul

title Abrir TODAS as contas (steam + jogo) - Task Bar Hero

cd /d "%~dp0\.."

if not exist src\abrir_steam.py (
  echo Modulo local abrir_steam.py ausente - nada a fazer.
  pause
  exit /b 0
)

echo A abrir as sandboxes em falta, cada uma na sua conta Steam...

echo (as janelas dos jogos aparecem aos poucos; o Steam entra sozinho em cada conta)

python -X utf8 src/abrir_steam.py --todas

pause

