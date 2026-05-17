@echo off
title NOVA BACKEND - ACTIVO
:LOOP
echo.
echo [!] Realizando limpieza preventiva de recursos...
ollama stop qwen3:8b >nul 2>&1
echo [+] Iniciando Motores de NOVA...
echo.
call venv\Scripts\activate.bat
python main.py
echo.
echo [!] EL SISTEMA SE HA DETENIDO O HA SOLICITADO REINICIO.
echo.
echo [+] Reiniciando automaticamente en 5 segundos...
echo [>] PRESIONE UNA TECLA (o Ctrl+C) PARA CANCELAR EL REINICIO.
echo.
timeout /t 5
if %errorlevel% neq 0 (
    echo [!] REINICIO CANCELADO POR EL USUARIO.
    pause
    exit
)
goto LOOP
