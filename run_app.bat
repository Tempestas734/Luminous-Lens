@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Demarrage de l'application Flask...
echo Python utilise : %PYTHON_EXE%
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"
"%PYTHON_EXE%" app.py

if errorlevel 1 (
    echo.
    echo L'application s'est arretee avec une erreur.
    pause
)
