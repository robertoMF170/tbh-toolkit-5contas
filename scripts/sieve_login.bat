@echo off
chcp 65001 >nul
title SIEVE - login (chave API, uma vez)
cd /d "%~dp0\.."
echo ============================================================
echo  SIEVE - aprovar acesso a API de scraping (uma vez)
echo ============================================================
echo  Vai aparecer um link + codigo. Abre o link no browser,
echo  confirma que o codigo e o mesmo e clica em Approve.
echo.
echo  AVISO: aprova SO um codigo que TU comecaste. Se nao pediste
echo         isto, nao aproves (pode ser phishing).
echo.
echo  A chave fica guardada em .env (nunca e impressa nem commitada).
echo ============================================================
echo.
python -X utf8 -u src/tbh_sieve.py --login
echo.
pause
