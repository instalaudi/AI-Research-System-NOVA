@echo off
title Autonomous Research AI System - Launcher (Global Python)
color 0b

echo ===================================================
echo        AUTONOMOUS RESEARCH AI SYSTEM
echo          (Using Global Python Environment)
echo ===================================================
echo.

:: Limpiar puertos ocupados
echo [+] Liberando puertos (8000, 3000)...
netstat -ano | findstr ":8000 " >nul 2>nul
if %errorlevel% equ 0 (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do (
        taskkill /PID %%a /F >nul 2>nul
    )
    echo [+] Puerto 8000 liberado.
)

netstat -ano | findstr ":3000 " >nul 2>nul
if %errorlevel% equ 0 (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 "') do (
        taskkill /PID %%a /F >nul 2>nul
    )
    echo [+] Puerto 3000 liberado.
)

timeout /t 2 /nobreak > nul

:: Verificar Python Global
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] ERROR: Python no esta instalado o no esta en el PATH.
    echo Por favor, instala Python y asegurate de marcar "Add Python to PATH".
    pause
    exit /b
)

:: Verificar Node.js
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] ERROR: Node.js no esta instalado.
    echo Por favor, instala Node.js desde https://nodejs.org/
    pause
    exit /b
)

:: Verificar dependencias frontend
if not exist frontend\node_modules (
    echo [!] Carpeta node_modules no encontrada. Instalando dependencias del frontend...
    cd frontend
    call npm install
    cd ..
    echo [+] Dependencias del frontend instaladas.
)

echo.
echo  [1/2] Iniciando Backend Agentico (FastAPI)...
:: Usar Python Global en lugar de venv
start "AI RESEARCH - BACKEND" cmd /k "cd backend && python main.py"

timeout /t 3 /nobreak > nul

echo.
echo  [2/2] Iniciando Interfaz (Next.js)...
start "AI RESEARCH - FRONTEND" cmd /k "cd frontend && npx next dev -H 0.0.0.0"

:: Abrir automaticamente la interfaz
echo.
echo  [+] Esperando a que los servicios esten listos...
timeout /t 8 /nobreak > nul
echo  [+] Abriendo navegador...
start http://localhost:3000

echo.
echo ===================================================
echo  SISTEMA INICIADO EXITOSAMENTE
echo.
echo  - INTERFAZ: http://localhost:3000
echo  - API:      http://localhost:8000
echo.
echo  Las ventanas de los servicios seguiran ejecutandose.
echo  Presione cualquier tecla para finalizar este lanzador.
echo ===================================================
pause > nul
