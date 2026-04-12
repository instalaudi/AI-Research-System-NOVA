@echo off
title Liberador de Puertos - AI Research System
color 0c

echo ===================================================
echo        LIBERADOR DE PUERTOS
echo ===================================================
echo.

echo [+] Buscando procesos en puerto 8000 (Backend)...
netstat -ano | findstr ":8000 " >nul 2>nul
if %errorlevel% equ 0 (
    echo [!] Encontrado proceso en puerto 8000
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do (
        echo [+] Matando PID %%a...
        taskkill /PID %%a /F
    )
    echo [OK] Puerto 8000 liberado
) else (
    echo [OK] Puerto 8000 ya esta libre
)

echo.
echo [+] Buscando procesos en puerto 3000 (Frontend)...
netstat -ano | findstr ":3000 " >nul 2>nul
if %errorlevel% equ 0 (
    echo [!] Encontrado proceso en puerto 3000
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 "') do (
        echo [+] Matando PID %%a...
        taskkill /PID %%a /F
    )
    echo [OK] Puerto 3000 liberado
) else (
    echo [OK] Puerto 3000 ya esta libre
)

echo.
echo ===================================================
timeout /t 2 /nobreak > nul
echo Presione cualquier tecla para continuar...
pause > nul
