@echo off
rem corrido pelo Agendador do Windows (TBH Monitor Baus) - sem janela, com log
cd /d "%~dp0\.."
if exist src/tbh_baus.py python -u src/tbh_baus.py --agora --silencioso >> baus_monitor.log 2>&1
