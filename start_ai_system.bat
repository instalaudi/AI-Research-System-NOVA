@echo off
SETLOCAL EnableExtensions
cd /d "%~dp0"
echo.
echo ===================================
echo   NOVA AI SYSTEM v2 (Elite 10/10)
echo ===================================
echo.
echo [+] Liberando puertos 8000 y 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " 2^>nul') do taskkill /PID %%a /F >nul 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " 2^>nul') do taskkill /PID %%a /F >nul 2>nul
echo [+] Lanzando Motores...
:: Lanzar Frontend en ventana separada
start "NOVA FRONTEND" cmd /k "cd frontend && npm run dev"

:: Lanzar Backend con el nuevo script de monitoreo (Watchdog)
start "NOVA BACKEND (WATCHDOG)" cmd /k "cd backend && run_with_watchdog.bat"
echo.
echo [+] Esperando inicio...
timeout /t 10 /nobreak >nul
start http://localhost:3000
echo.
echo [OK] SISTEMA ACTIVO.
pause
