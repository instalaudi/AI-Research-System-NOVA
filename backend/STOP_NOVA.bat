@echo off
title FINALIZANDO NOVA...
echo.
echo [!] Cerrando todos los servicios de NOVA AI...
echo.

:: Matar procesos de Python relacionados con el sistema
taskkill /F /IM python.exe /T >nul 2>&1

:: Detener el modelo en Ollama para liberar CPU/RAM
echo [!] Liberando potencia de Ollama...
ollama stop qwen3:8b >nul 2>&1
ollama stop llama3.1:8b >nul 2>&1
ollama stop qwen2.5-coder:7b >nul 2>&1

echo.
echo [OK] Sistema detenido y recursos liberados.
echo.
pause
