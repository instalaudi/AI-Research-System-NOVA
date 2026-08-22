@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8:replace
color 0B
:: ==========================================
:: NOVA AI - LANZADOR OFICIAL UNIFICADO
:: ==========================================

echo Limpiando puertos conocidos antes de iniciar...
for %%p in (9999 8000 3000 11438 11439 11440 11441) do (
    for /f "tokens=5" %%a in ('netstat -ano -p tcp ^| findstr /r /c:":%%p[ ]" ^| findstr "LISTENING"') do (
        echo Cerrando proceso PID %%a en puerto %%p 2>nul
        taskkill /PID %%a /F 2>nul
    )
)
timeout /t 2 /nobreak >nul



cd /d "%~dp0control_center"
if errorlevel 1 (
    echo [ERROR] No se pudo encontrar la carpeta control_center.
    pause
    exit /b 1
)

call start_control_center.bat
if errorlevel 1 (
    color 0C
    echo.
    echo [ERROR] Hubo un problema al iniciar el Control Center.
    echo         Revisa el mensaje anterior en esta ventana.
    echo.
    pause
    exit /b 1
)
