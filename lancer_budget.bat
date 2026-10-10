@echo off
title Carnet
cd /d "%~dp0"
set PYTHON=python
if exist ".venv\Scripts\python.exe" set PYTHON=.venv\Scripts\python.exe
start "" http://localhost:8500
"%PYTHON%" backend\app.py
pause
