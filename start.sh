#!/bin/bash

# Autonomous Research AI System - Launcher for Linux/macOS

echo "==================================================="
echo "       AUTONOMOUS RESEARCH AI SYSTEM"
echo "==================================================="

# -- VERIFICACIONES ----------------------------------

command -v python3 >/dev/null 2>&1 || { echo "[!] Python3 no encontrado."; exit 1; }
command -v node >/dev/null 2>&1 || { echo "[!] Node.js no encontrado."; exit 1; }

# Verificar versión Python >= 3.10
python3 -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" || {
    echo "[!] Se requiere Python 3.10 o superior."
    exit 1
}

# Verificar Ollama corriendo
curl -s http://localhost:11434 >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "[!] ADVERTENCIA: Ollama no detectado en localhost:11434"
    read -p "¿Continuar de todas formas? (s/n): " choice
    [[ "$choice" != "s" ]] && exit 1
fi

# -- LIBERAR PUERTOS ----------------------------------

for port in 8000 3000; do
    pid=$(lsof -t -i:$port)
    if [ ! -z "$pid" ]; then
        echo "[+] Liberando puerto $port (PID $pid)..."
        kill -9 $pid
    fi
done

# -- BACKEND -----------------------------------------

pushd backend > /dev/null

if [ ! -d "venv" ]; then
    echo "[+] Creando entorno virtual..."
    python3 -m venv venv || { echo "[!] Error creando venv."; popd > /dev/null; exit 1; }
fi

source venv/bin/activate
pip install -r requirements.txt -q
echo "[+] Backend listo."

popd > /dev/null

# -- FRONTEND ----------------------------------------

pushd frontend > /dev/null

if [ ! -d "node_modules" ] || [ package.json -nt .package.json.bak ]; then
    echo "[+] Instalando dependencias del frontend..."
    npm install
    cp package.json .package.json.bak
fi

popd > /dev/null

# -- ARRANQUE ----------------------------------------

echo "[1/2] Iniciando Backend..."
(cd backend && source venv/bin/activate && python3 main.py) &
BACKEND_PID=$!

echo "[2/2] Iniciando Frontend..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

# -- ESPERAR HEALTH CHECK REAL -----------------------
echo "[+] Esperando que el backend responda..."
MAX_WAIT=30
WAITED=0

while [ $WAITED -lt $MAX_WAIT ]; do
    sleep 2
    WAITED=$((WAITED + 2))
    curl -s http://localhost:8000/health >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "[+] Backend activo."
        break
    fi
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "[!] Backend tardó demasiado. Verifica los logs."
fi

echo ""
echo "==================================================="
echo " SISTEMA INICIADO"
echo " - Interfaz: http://localhost:3000"
echo " - API:      http://localhost:8000/docs"
echo "==================================================="
echo "Presione Ctrl+C para detener el sistema."

# Mantener el script corriendo y manejar el cierre
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT TERM
wait
