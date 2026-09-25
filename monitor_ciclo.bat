@echo off
rem corrido pelo Agendador do Windows (TBH Monitor Baus) - sem janela, com log
cd /d "%~dp0"
python -u tbh_baus.py --agora --silencioso >> baus_monitor.log 2>&1
