@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8:replace
SETLOCAL EnableExtensions
cd /d "%~dp0"
color 0B

echo.
echo   [ NOVA AI - RESEARCH SYSTEM ]
echo   -----------------------------
echo   Iniciando nodo de control...
echo.

:: Select Python Interpreter (prefer virtual environment)
set "PY_EXEC=python"
if exist "%~dp0..\backend\venv\Scripts\python.exe" (
    set "PY_EXEC=%~dp0..\backend\venv\Scripts\python.exe"
)

:: Check Python
"%PY_EXEC%" --version >nul 2>nul
if errorlevel 1 (
    color 0C
    echo [ERROR] Python no encontrado en el entorno ni en PATH.
    pause & exit /b 1
)

:: Install dependencies if needed
echo [+] Verificando subsistemas...
"%PY_EXEC%" -c "import fastapi, uvicorn, psutil, httpx" >nul 2>nul
if errorlevel 1 (
    echo [+] Inicializando dependencias criticas...
    "%PY_EXEC%" -m pip install fastapi uvicorn[standard] psutil httpx python-dotenv --quiet
    if errorlevel 1 (
        color 0C
        echo [ERROR] No se pudieron instalar dependencias. Ejecuta:
        echo        pip install fastapi uvicorn[standard] psutil httpx python-dotenv
        pause & exit /b 1
    )
)

:: Liberar puerto 9999 si quedo un launcher zombie
echo [+] Comprobando puerto 9999...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "127.0.0.1:9999" ^| findstr LISTENING') do (
    echo [+] Cerrando proceso anterior en puerto 9999 ^(PID %%a^)...
    taskkill /PID %%a /F /T >nul 2>nul
)
timeout /t 1 /nobreak >nul

echo [+] Puertos de enlace: 9999 / 8000 / 3000
echo [+] Puertos Ollama: 11438 / 11439 / 11440
echo [+] Nodo de control: http://localhost:9999
echo.
echo  Use el Control Center para gestionar el sistema.
echo  Cierre esta ventana solo al terminar.
echo.

:: Open browser after short delay (background)
start /b cmd /c "ping -n 4 127.0.0.1 >nul && start http://localhost:9999"

:: Run launcher (this is the ONLY terminal window)
"%PY_EXEC%" launcher_server.py
set LAUNCHER_EXIT=%ERRORLEVEL%


if not "%LAUNCHER_EXIT%"=="0" (
    color 0C
    echo.
    echo [ERROR] El Control Center termino con codigo %LAUNCHER_EXIT%.
    echo         Causas habituales: puerto 9999 ocupado, falta httpx/psutil, o cierre manual.
    echo         Prueba: netstat -ano ^| findstr :9999
    pause
    exit /b %LAUNCHER_EXIT%
)

pause
exit /b 0
