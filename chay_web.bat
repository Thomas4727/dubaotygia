@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo Dang mo web tai http://localhost:5000  (dong cua so nay de tat web)
start "" http://localhost:5000
".venv\Scripts\python.exe" app.py
pause
