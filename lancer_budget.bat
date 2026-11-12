@echo off
title Carnet
cd /d "%~dp0"
set PYTHON=python
if exist ".venv\Scripts\python.exe" set PYTHON=.venv\Scripts\python.exe
rem Frontend pas encore construit (dist\ n'est pas versionne) : npm ci + npm run build
if not exist "frontend-react\dist\index.html" (
  "%PYTHON%" backend\construire_frontend.py || (pause & exit /b 1)
)
start "" http://localhost:8500
"%PYTHON%" backend\app.py
pause
