@echo off
TITLE NOVA Multi-Engine Manager
echo [NOVA] Iniciando Enjambre de Motores LLM...

:: Configuración de Puertos
set OLLAMA_HOST_1=11438
set OLLAMA_HOST_2=11439
set OLLAMA_HOST_3=11440

:: Motor 1: Chat/General (Puerto 11438) - Núcleos 0-3 (Afinidad 0F)
echo [Motor 1] Iniciando Chat Engine en puerto %OLLAMA_HOST_1% (Núcleos 0-3)...
start "Ollama Chat" /affinity 0F /min cmd /c "set OLLAMA_HOST=0.0.0.0:%OLLAMA_HOST_1% && ollama serve"

:: Motor 2: Developer (Puerto 11439) - Núcleos 4-7 (Afinidad F0)
echo [Motor 2] Iniciando Dev Engine en puerto %OLLAMA_HOST_2% (Núcleos 4-7)...
start "Ollama Dev" /affinity F0 /min cmd /c "set OLLAMA_HOST=0.0.0.0:%OLLAMA_HOST_2% && ollama serve"

:: Motor 3: Auditoria/Vision (Puerto 11440) - Núcleos 0-7 (Afinidad FF - Compartido)
echo [Motor 3] Iniciando Auditor Engine en puerto %OLLAMA_HOST_3% (Todos los núcleos)...
start "Ollama Audit" /affinity FF /min cmd /c "set OLLAMA_HOST=0.0.0.0:%OLLAMA_HOST_3% && ollama serve"

echo.
echo [!] Motores iniciados en segundo plano.
echo [!] Monitorea el uso de RAM (Máximo recomendado 24GB).
echo [!] NOVA Router redirigirá el tráfico automáticamente.
echo [!] NOVA Router redirigirá el tráfico automáticamente.
timeout /t 5 /nobreak >nul
