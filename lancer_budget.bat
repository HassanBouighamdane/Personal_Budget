@echo off
title Mon Budget
cd /d "%~dp0backend"
start "" http://localhost:8500
python app.py
pause
