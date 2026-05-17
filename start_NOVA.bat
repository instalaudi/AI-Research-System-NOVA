@echo off
chcp 65001 >nul
color 0B
:: ==========================================
:: NOVA AI - LANZADOR OFICIAL UNIFICADO
:: ==========================================

cd /d "%~dp0control_center"
if errorlevel 1 (
    echo [ERROR] No se pudo encontrar la carpeta control_center.
    pause
    exit /b 1
)

call start_control_center.bat
if errorlevel 1 (
    echo [ERROR] Hubo un problema al iniciar el Control Center.
    pause
)
