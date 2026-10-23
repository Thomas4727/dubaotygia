@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
title Chia se web Du bao ty gia
".venv\Scripts\python.exe" chia_se.py %*
pause
