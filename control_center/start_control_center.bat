@echo off
chcp 65001 >nul
SETLOCAL EnableExtensions
cd /d "%~dp0"
color 0B

echo.
echo   [ NOVA AI - RESEARCH SYSTEM ]
echo   -----------------------------
echo   Iniciando nodo de control...
echo.

:: Check Python
python --version >nul 2>nul
if errorlevel 1 (
    color 0C
    echo [ERROR] Python no encontrado en PATH.
    pause & exit /b 1
)

:: Install dependencies if needed
echo [+] Verificando subsistemas...
python -c "import fastapi, uvicorn, psutil" >nul 2>nul
if errorlevel 1 (
    echo [+] Inicializando dependencias criticas...
    pip install fastapi uvicorn[standard] psutil httpx --quiet
)

echo [+] Puertos de enlace: 9999 / 8000 / 3000
echo [+] Nodo de control: http://localhost:9999
echo.
echo  Use el Control Center para gestionar el sistema.
echo  Cierre esta ventana solo al terminar.
echo.

:: Open browser after short delay (background)
start /b cmd /c "ping -n 3 127.0.0.1 >nul && start http://localhost:9999"

:: Run launcher (this is the ONLY terminal window)
python launcher_server.py

pause
