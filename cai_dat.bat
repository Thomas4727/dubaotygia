@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Tao moi truong Python .venv ...
    py -m venv .venv || goto :loi
) else (
    echo [1/3] Da co moi truong .venv
)

echo [2/3] Cai thu vien ...
".venv\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cpu || goto :loi
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :loi

echo [3/3] Tao database trong SQL Server ...
".venv\Scripts\python.exe" khoi_tao_db.py || goto :loi

echo.
echo Cai dat xong! Bam dup vao chay_web.bat de mo web.
pause
exit /b 0

:loi
echo.
echo Co loi xay ra, xem thong bao phia tren.
pause
exit /b 1
