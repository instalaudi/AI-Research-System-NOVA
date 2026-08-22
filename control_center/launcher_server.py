"""
NOVA Control Center - Launcher Server
Run this once. It manages Backend, Frontend, and Ollama engines.
Access the UI at: http://localhost:9999
"""
import asyncio
import json
import os
import subprocess
import threading
import sys
import time
from collections import deque
from pathlib import Path
from typing import AsyncGenerator, Optional

# v13.9.5: Asegurar UTF-8 en subprocesos Windows
os.environ['PYTHONIOENCODING'] = 'utf-8:replace'

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
import uvicorn
import psutil

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None
import secrets

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
CONFIG_FILE  = BASE_DIR / "nova_launcher.json"
HTML_FILE    = BASE_DIR / "control_center.html"

# Load environment configuration
if load_dotenv:
    load_dotenv(PROJECT_ROOT / "backend" / ".env")
    load_dotenv(PROJECT_ROOT / ".env")
else:
    for env_file in [PROJECT_ROOT / "backend" / ".env", PROJECT_ROOT / ".env"]:
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass

# ── Security ──────────────────────────────────────────────────────────────────
CC_API_KEY = os.getenv("CC_API_KEY")

if not CC_API_KEY or CC_API_KEY == "nova-cc-cambiar-en-produccion":
    CC_API_KEY = secrets.token_urlsafe(32)
    os.environ["CC_API_KEY"] = CC_API_KEY

CC_AUTH_HEADER = "X-CC-API-Key"


# ── Default Config ─────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "services": {
        "warmup_delay": 10,
        "num_ollama_engines": 3
    },
    "models": {
        "LLM_FAST_MODEL":  "qwen2.5:1.5b",
        "LLM_MODEL_NAME":  "qwen2.5:1.5b",
        "LLM_CODER_MODEL": "qwen2.5:1.5b",
        "LLM_THINKER_MODEL": "qwen2.5:1.5b",
        "DISTILL_MODEL_REASONING": "qwen2.5:1.5b",
        "DISTILL_MODEL_GENERAL": "qwen2.5:1.5b",
        "LLM_EMBED_MODEL": "all-MiniLM-L6-v2",
        "LLM_AUDIT_MODEL": "phi3:mini",
        "LLM_VISION_MODEL": "llava-llama3:latest",
        "OLLAMA_URL":      "http://localhost:11438/api/chat",
        "LLM_DEV_URL":     "http://localhost:11439/api/chat",
        "LLM_AUDIT_URL":   "http://localhost:11440/api/chat",
    },
    "performance": {
        "RATE_LIMIT_REQUESTS":    "100",
        "RATE_LIMIT_WINDOW":      "60",
        "CHAT_HISTORY_MAX_SIZE":  "100",
        "MAX_QUERY_LENGTH":       "50000",
        "COGNITIVE_MODE":         "balanced"
    },
    "features": {
        "DISTILLATION":   "true",
        "EVOLUTION":      "true",
        "PROACTIVE":      "true",
        "TELEGRAM_MODE":  "polling",
        "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
        "OLLAMA_NO_CLOUD": "1"
    }
}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy

def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def _ollama_ports_to_probe() -> list[int]:
    """Puertos de los 3 motores configurados en nova_launcher.json."""
    from urllib.parse import urlparse
    ports: list[int] = []
    models_cfg = load_config().get("models", {})
    for key in ("OLLAMA_URL", "LLM_DEV_URL", "LLM_AUDIT_URL"):
        url = models_cfg.get(key, "")
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.port and parsed.port not in ports:
            ports.append(parsed.port)
    for svc in ("ollama_1", "ollama_2", "ollama_3"):
        p = SERVICES.get(svc, {}).get("port")
        if p and p not in ports:
            ports.append(p)
    return ports

# ── Service Registry ───────────────────────────────────────────────────────────
SERVICES = {
    "backend":  {"port": 8000},
    "frontend": {"port": 3000},
    "ollama_1": {"port": 11438},
    "ollama_2": {"port": 11439},
    "ollama_3": {"port": 11440},
}

LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

_state: dict[str, dict] = {
    name: {
        "proc":   None,
        "status": "stopped",   # stopped | starting | running | error
        "logs":   deque(maxlen=5000),
        "pid":    None,
        "total_count": 0,
        "logfile_path": LOGS_DIR / f"logs_{name}.txt"
    }
    for name in SERVICES
}

# ── Helpers ────────────────────────────────────────────────────────────────────
def _log(svc: str, line: str):
    clean_line = line.rstrip("\n\r")
    _state[svc]["logs"].append(clean_line)
    _state[svc]["total_count"] += 1
    
    try:
        log_path = _state[svc].get("logfile_path")
        if log_path:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(clean_line + "\n")
    except Exception:
        pass

def _pipe_reader(svc: str, stream):
    """Reads subprocess stdout in a background thread and decodes bytes safely."""
    try:
        for line in stream:
            if not line: break
            if isinstance(line, bytes):
                line = line.decode('utf-8', errors='replace')
            _log(svc, line)
    except Exception:
        pass

def _build_env(cfg: dict) -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    for section in ("models", "performance", "features"):
        for k, v in cfg.get(section, {}).items():
            env[k] = str(v)
    return env

def _kill_port(port: int, wait_seconds: int = 5):
    """Force-kills any process occupying a TCP port (Windows only) and waits for it to be released.
    HOTFIX v13.9.1: Mejorar parsing robusto de netstat y proteger contra matar launcher.
    """
    if os.name != "nt": return
    import psutil
    import time
    import re

    launcher_pid = os.getpid()  # No matar al launcher mismo

    def _get_pids():
        pids = set()
        # HOTFIX: Usar regex para parsear netstat de forma robusta, incluyendo IPv6 y direcciones entre corchetes.
        try:
            output = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, encoding='latin-1', errors='replace', shell=False)
            if output.returncode == 0:
                # Regex para parsear líneas de netstat con local:port y PID.
                # Ejemplos válidos:
                # TCP    127.0.0.1:9999    0.0.0.0:0    LISTENING    2492
                # TCP    [::]:11440    [::]:0    LISTENING    1234
                pattern = r"^\s*TCP\s+(.+?):(\d+)\s+(.+?):\d+\s+\S+\s+(\d+)"
                for line in output.stdout.splitlines():
                    match = re.search(pattern, line)
                    if match:
                        port_num = int(match.group(2))
                        pid = int(match.group(4))
                        if port_num == port and pid > 0 and pid != launcher_pid:
                            pids.add(pid)
        except Exception:
            pass

        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.laddr and conn.laddr.port == port:
                    if conn.pid and conn.pid > 0 and conn.pid != launcher_pid:
                        pids.add(conn.pid)
        except Exception:
            pass
        return pids

    for _ in range(3): # Try killing up to 3 times
        pids = _get_pids()
        if not pids: break
        
        for pid in pids:
            print(f"[Launcher] Force killing PID {pid} on port {port}")
            try:
                proc = psutil.Process(pid)
                try:
                    for child in proc.children(recursive=True):
                        try:
                            child.kill()
                        except Exception:
                            pass
                except Exception:
                    pass
                proc.kill()
            except Exception:
                # Final fallback to taskkill
                subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], 
                               capture_output=True, text=True, encoding='latin-1', errors='replace', shell=False)
        
        # Wait a bit for the OS to release the socket
        time.sleep(1)

    # Final check
    start_time = time.time()
    while time.time() - start_time < wait_seconds:
        if not _get_pids():
            return True
        time.sleep(0.5)
    
    return not _get_pids()


def _kill_tree(pid: int):
    """Kills process and all children (cross-platform)."""
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except Exception:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                           capture_output=True, text=True, encoding='latin-1', errors='replace')

def _cleanup_ollama_blobs(svc: str):
    """v13.6: Limpia archivos de modelos parciales/corruptos de Ollama antes de arrancar."""
    try:
        # Ruta típica de Ollama en Windows
        models_dir = Path.home() / ".ollama" / "models" / "blobs"
        if not models_dir.exists(): return
        
        _log(svc, "[Launcher] 🧹 Limpiando caché de modelos corruptos...")
        count = 0
        # Buscamos archivos que terminen en -partial o tengan patrones de descarga fallida
        for p in models_dir.glob("*-partial*"):
            try:
                p.unlink()
                count += 1
            except Exception:
                pass
        if count > 0:
            _log(svc, f"[Launcher] ✨ Se limpiaron {count} fragmentos de descarga fallida.")
    except Exception as e:
        _log(svc, f"[Launcher] ⚠️ No se pudo limpiar la caché de modelos: {e}")

def _check_backend_deps(python_exe: str, cwd: str, svc: str):
    """v13.5: Verifica e instala dependencias faltantes en el backend antes de arrancar."""
    req_file = os.path.join(cwd, "requirements.txt")
    if not os.path.exists(req_file): return

    _log(svc, "[Launcher] 🔍 Verificando integridad de librerías...")
    try:
        # Intento rápido de ver si faltan librerías críticas
        check_cmd = [python_exe, "-c", "import browser_use, lightrag, playwright, pyautogui, cv2"]
        result = subprocess.run(check_cmd, cwd=cwd, capture_output=True, text=True, encoding='latin-1', errors='replace')
        
        if result.returncode != 0:
            _log(svc, "[Launcher] 📦 Detectadas librerías faltantes. Instalando dependencias (esto puede tardar)...")
            try:
                # Ejecutar pip install
                install_cmd = [python_exe, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"]
                subprocess.run(install_cmd, cwd=cwd, check=False, text=True, encoding='latin-1', errors='replace')
                
                # Caso especial: Playwright necesita instalar sus navegadores
                _log(svc, "[Launcher] 🌐 Configurando motores de navegación...")
                subprocess.run([python_exe, "-m", "playwright", "install", "chromium"], cwd=cwd, check=False, text=True, encoding='latin-1', errors='replace')
                _log(svc, "[Launcher] ✅ Dependencias actualizadas.")
            except Exception as pip_err:
                _log(svc, f"[Launcher] ⚠️ No se pudieron instalar dependencias completamente: {pip_err}")
        else:
            _log(svc, "[Launcher] ✅ Salud de librerías: OK")
    except Exception as e:
        _log(svc, f"[Launcher] ⚠️ Advertencia en auto-instalación: {e}")

# ── Service Lifecycle ──────────────────────────────────────────────────────────
def start_service(svc: str):
    cfg   = load_config()
    state = _state[svc]

    # Respect num_ollama_engines limit
    if svc.startswith("ollama"):
        idx = int(svc.split("_")[1])
        if idx > cfg["services"].get("num_ollama_engines", 3):
            _log(svc, f"[Launcher] Engine {idx} is disabled (num_engines={cfg['services']['num_ollama_engines']})")
            return

    env  = _build_env(cfg)
    IS_WIN = os.name == "nt"

    # Build command
    if svc == "backend":
        cwd = str(PROJECT_ROOT / "backend")
        # v12.0.1: Prioridad al entorno virtual si existe
        venv_python = PROJECT_ROOT / "backend" / "venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            # Fallback a Linux path o global
            venv_python = PROJECT_ROOT / "backend" / "venv" / "bin" / "python"
        
        python_exe = str(venv_python) if venv_python.exists() else sys.executable
        
        # v13.5: Auto-fix dependencies before start
        _check_backend_deps(python_exe, cwd, svc)

        cmd = [python_exe, "-m", "uvicorn", "main:app",
               "--host", "0.0.0.0", "--port", "8000"]
        shell = False

    elif svc == "frontend":
        cwd   = str(PROJECT_ROOT / "frontend")
        cmd   = ["npm.cmd", "run", "dev"] if IS_WIN else ["npm", "run", "dev"]
        shell = False

    elif svc.startswith("ollama"):
        port = SERVICES.get(svc, {}).get("port", 11437 + int(svc.split("_")[1]))
        env["OLLAMA_HOST"] = f"127.0.0.1:{port}"
        # Un modelo cargado por motor → menos RAM en reposo
        env.setdefault("OLLAMA_NUM_PARALLEL", "1")
        env.setdefault("OLLAMA_MAX_LOADED_MODELS", "1")

        # v13.6: Limpiar basura de modelos antes de arrancar Ollama
        _cleanup_ollama_blobs(svc)
        
        cwd   = str(PROJECT_ROOT)
        cmd   = ["ollama", "serve"]
        shell = False
    else:
        return
        
    # v11.8.4: Always kill the mapped port before starting the subprocess 
    # to avoid "Only one usage of each socket address" error
    svc_port = SERVICES.get(svc, {}).get("port")
    if svc_port:
        _kill_port(svc_port)

    try:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            text=False,
            shell=shell,
            creationflags=creationflags,
        )

        state["proc"]   = proc
        state["pid"]    = proc.pid
        state["status"] = "starting"
        _log(svc, f"[Launcher] ▶ Started — PID {proc.pid}")

        # Pipe reader thread
        threading.Thread(target=_pipe_reader, args=(svc, proc.stdout), daemon=True).start()

        # Monitor thread — marks as stopped when process exits
        def _monitor():
            proc.wait()
            state["status"] = "stopped"
            state["proc"]   = None
            _log(svc, f"[Launcher] ■ Exited (code {proc.returncode})")

        threading.Thread(target=_monitor, daemon=True).start()
        state["status"] = "running"

    except FileNotFoundError as e:
        state["status"] = "error"
        _log(svc, f"[Launcher] ✗ Command not found: {e}. Is it installed and in PATH?")
    except Exception as e:
        state["status"] = "error"
        _log(svc, f"[Launcher] ✗ Error starting: {e}")


def stop_service(svc: str):
    state = _state[svc]
    proc  = state.get("proc")
    _log(svc, f"[Launcher] ■ Stopping {svc}...")
    if proc and proc.poll() is None:
        try:
            _kill_tree(proc.pid)
            _log(svc, f"[Launcher] ■ Process tree {proc.pid} terminated.")
        except Exception as e:
            _log(svc, f"[Launcher] Stop error: {e}")
    state["status"] = "stopped"
    state["proc"]   = None
    state["pid"]    = None
    _kill_port(SERVICES[svc]["port"])
    _log(svc, f"[Launcher] ■ Cleaned port {SERVICES[svc]['port']}")


def restart_service(svc: str):
    _log(svc, "[Launcher] ↺ Restarting...")
    stop_service(svc)
    time.sleep(2)
    start_service(svc)


# ── FastAPI ────────────────────────────────────────────────────────────────────
app = FastAPI(title="NOVA Launcher", docs_url=None, redoc_url=None)
# FIX C-2 (Auditoría v11.9.18): Restringir CORS al propio Control Center
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:9999", "http://127.0.0.1:9999"], allow_methods=["*"], allow_headers=["*"])


# A dictionary of active short-lived tokens: {token: expiration_timestamp}
_active_tokens = {}

def _validate_temp_token(token: str) -> bool:
    # Clean up expired tokens
    now = time.time()
    expired = [t for t, exp in _active_tokens.items() if now > exp]
    for t in expired:
        _active_tokens.pop(t, None)
        
    return token in _active_tokens

def _require_api_key(request):
    """Valida el API key en todos los endpoints de la API (GET, POST, DELETE, etc.).
    Para streams/EventSource, se permite validación vía token de un solo uso o query param 'key'.
    v13.9.1 HOTFIX: Corregir validación para permitir token temporal sin header
    """
    # Intentar validar por header X-CC-API-Key
    provided = request.headers.get(CC_AUTH_HEADER, "").strip()
    if provided:
        if provided == CC_API_KEY:
            return
        # Si hay header pero es inválido, rechazar directamente
        raise HTTPException(status_code=403, detail="Invalid X-CC-API-Key header")
    
    # Si no hay header, intentar por query param 'key'
    provided_key = request.query_params.get("key", "").strip()
    if provided_key:
        if provided_key == CC_API_KEY:
            return
        # Si hay key pero es inválida, rechazar directamente
        raise HTTPException(status_code=403, detail="Invalid API key parameter")
    
    # Si no hay header ni key, intentar por token temporal (para streams)
    provided_token = request.query_params.get("token", "").strip()
    if provided_token and _validate_temp_token(provided_token):
        return
    
    # Si llegamos aquí, ningún método de autenticación funcionó
    raise HTTPException(status_code=403, detail="Missing or invalid authentication (header, key, or token)")


@app.post("/api/auth/token")
async def api_get_temp_token(request: Request):
    # Requiere el API key real en las cabeceras para emitir un token de corta duración
    _require_api_key(request)
    import uuid
    token = str(uuid.uuid4())
    _active_tokens[token] = time.time() + 10.0 # Válido por 10 segundos
    return {"token": token}




@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    if HTML_FILE.exists():
        content = HTML_FILE.read_text(encoding="utf-8")
        # Inyectar dinámicamente el API Key en el frontend para evitar hardcoding
        content = content.replace("nova-cc-cambiar-en-produccion", CC_API_KEY)
        return content
    return "<h1>control_center.html not found next to launcher_server.py</h1>"


@app.get("/api/status")
async def api_status(request: Request):
    _require_api_key(request)
    out = {}
    for svc, info in SERVICES.items():
        s     = _state[svc]
        proc  = s["proc"]
        alive = proc is not None and proc.poll() is None
        if alive and s["status"] not in ("running", "starting"):
            s["status"] = "running"
        elif not alive and s["status"] == "running":
            s["status"] = "stopped"

        out[svc] = {
            "status": s["status"],
            "port":   info["port"],
            "pid":    s["pid"] if alive else None,
        }

    mem = psutil.virtual_memory()
    out["_system"] = {
        "ram_percent":  round(mem.percent, 1),
        "ram_used_gb":  round(mem.used  / 1e9, 1),
        "ram_total_gb": round(mem.total / 1e9, 1),
        "cpu_percent":  psutil.cpu_percent(interval=None),
    }
    return out


@app.post("/api/service/{svc}/start")
async def api_start(svc: str, request: Request):
    _require_api_key(request)
    if svc not in _state: raise HTTPException(404, "Unknown service")
    threading.Thread(target=start_service, args=(svc,), daemon=True).start()
    return {"ok": True}


@app.post("/api/service/{svc}/stop")
async def api_stop(svc: str, request: Request):
    _require_api_key(request)
    if svc not in _state: raise HTTPException(404, "Unknown service")
    threading.Thread(target=stop_service, args=(svc,), daemon=True).start()
    return {"ok": True}


@app.post("/api/service/{svc}/restart")
async def api_restart(svc: str, request: Request):
    _require_api_key(request)
    if svc not in _state: raise HTTPException(404, "Unknown service")
    threading.Thread(target=restart_service, args=(svc,), daemon=True).start()
    return {"ok": True}


@app.post("/api/services/start-all")
async def api_start_all(request: Request):
    _require_api_key(request)
    cfg = load_config()

    def _sequence():
        import httpx
        num = cfg["services"].get("num_ollama_engines", 3)
        for i in range(1, num + 1):
            start_service(f"ollama_{i}")

        # v13.6.1: Improved health check loop for Ollama
        max_wait = cfg["services"].get("warmup_delay", 30)
        _log("backend", f"[Launcher] ⏳ Waiting for Ollama (max {max_wait}s)...")
        
        ollama_ready = False
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                # Use a small timeout for the check
                with httpx.Client(timeout=2.0) as client:
                    port_1 = SERVICES.get("ollama_1", {}).get("port", 11438)
                    resp = client.get(f"http://127.0.0.1:{port_1}/api/tags")
                    if resp.status_code == 200:
                        ollama_ready = True
                        break
            except Exception:
                pass
            time.sleep(2)
        
        if ollama_ready:
            _log("backend", "[Launcher] ✅ Ollama is responding.")
        else:
            _log("backend", "[Launcher] ⚠️ Ollama did not respond in time, starting backend anyway...")

        start_service("backend")
        time.sleep(3)
        start_service("frontend")


    threading.Thread(target=_sequence, daemon=True).start()
    return {"ok": True}


@app.post("/api/services/stop-all")
async def api_stop_all(request: Request):
    _require_api_key(request)
    print("[Launcher] Stop all requested")
    for svc in list(_state.keys()):
        threading.Thread(target=stop_service, args=(svc,), daemon=True).start()
    return {"ok": True}


@app.get("/api/logs/{svc}")
async def api_logs(svc: str, lines: int = 150, request: Request = None):
    _require_api_key(request)
    if svc not in _state: raise HTTPException(404, "Unknown service")
    return {"logs": list(_state[svc]["logs"])[-lines:]}


@app.delete("/api/logs/{svc}")
async def api_clear_logs(svc: str, request: Request):
    _require_api_key(request)
    if svc not in _state: raise HTTPException(404, "Unknown service")
    _state[svc]["logs"].clear()
    return {"ok": True}


@app.get("/api/ollama/models")
async def api_get_ollama_models(request: Request):
    _require_api_key(request)
    """v11.9.18: Fetch available models from Ollama to avoid typing errors."""
    import httpx
    last_error = "Ollama no responde"
    merged: list[str] = []
    active_ports: list[int] = []
    for port in _ollama_ports_to_probe():
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"http://127.0.0.1:{port}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    active_ports.append(port)
                    for m in data.get("models", []):
                        name = m.get("name")
                        if name and name not in merged:
                            merged.append(name)
                else:
                    last_error = f"puerto {port}: HTTP {resp.status_code}"
        except Exception as e:
            last_error = f"puerto {port}: {e}"
    if merged:
        return {"models": merged, "ports": active_ports}
    return {"models": [], "error": last_error}


@app.get("/api/logs/{svc}/stream")
async def api_log_stream(svc: str, request: Request):
    _require_api_key(request)
    if svc not in _state: raise HTTPException(404, "Unknown service")

    async def _generate() -> AsyncGenerator[str, None]:
        try:
            # Sync pointer BEFORE sending existing buffer to avoid race condition
            sent_total = _state[svc]["total_count"]
            
            # Start by sending the current buffer
            current_logs = list(_state[svc]["logs"])
            for line in current_logs:
                yield f"data: {json.dumps({'line': line})}\n\n"
            
            while True:
                await asyncio.sleep(0.25)
                total = _state[svc]["total_count"]
                if total > sent_total:
                    new_logs_count = min(total - sent_total, 600)
                    logs = list(_state[svc]["logs"])
                    to_send = logs[-new_logs_count:]
                    for line in to_send:
                        yield f"data: {json.dumps({'line': line})}\n\n"
                    sent_total = total
        except asyncio.CancelledError:
            pass # Ignorar error de cancelación cuando el usuario apaga el Control Center o recarga la página

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/config")
async def api_get_config(request: Request):
    _require_api_key(request)
    return load_config()


@app.post("/api/config")
async def api_set_config(body: dict, request: Request):
    _require_api_key(request)
    cfg = load_config()
    # FIX M-1 (Auditoría v11.9.18): Whitelist de secciones permitidas
    ALLOWED_SECTIONS = {"models", "performance", "features", "services"}
    
    # Validaciones y conversiones de tipos para la sección services
    if "services" in body and isinstance(body["services"], dict):
        s = body["services"]
        if "num_ollama_engines" in s:
            try:
                s["num_ollama_engines"] = int(s["num_ollama_engines"])
            except (ValueError, TypeError):
                raise HTTPException(400, "num_ollama_engines must be an integer")
        if "warmup_delay" in s:
            try:
                s["warmup_delay"] = int(s["warmup_delay"])
            except (ValueError, TypeError):
                raise HTTPException(400, "warmup_delay must be an integer")

    for section, values in body.items():
        if section not in ALLOWED_SECTIONS:
            raise HTTPException(400, f"Section '{section}' not allowed")
        if section in cfg and isinstance(cfg[section], dict):
            cfg[section].update(values)
        else:
            cfg[section] = values
    save_config(cfg)
    return {"ok": True, "config": cfg}


# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    # v11.9.11: Forzar UTF-8 en salida de terminal para evitar símbolos extraños
    if sys.platform == "win32":
        import os
        os.system("chcp 65001 > nul")
        
    print()
    print(r"   _  _  _____  _   _   _   ")
    print(r"  | \| ||  _  || | | | /_\  ")
    print(r"  | .  || |_| || \_/ |/ _ \ ")
    print(r"  |_|\_||_____| \___//_/ \_\ ")
    print(r"   Autonomous Research AI v14.0.0 Tier S")
    print(r"  ------------------------------------------")
    print(r"   Control Node: http://localhost:9999")
    print()
    # FIX C-2 (Auditoría v11.9.18): Bind a 127.0.0.1 — solo acceso local

    def _force_free_port(port, max_attempts=5):
        import time, os
        for attempt in range(max_attempts):
            try:
                out = os.popen(f'netstat -ano | findstr :{port}').read()
                if not out:
                    print(f"[Launcher] Puerto {port} libre")
                    return
                # Mata todos los PIDs reales (distintos de 0) que usan el puerto
                pids = set()
                for line in out.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 5:
                        p = parts[-1].strip()
                        if p.isdigit() and int(p) > 0:
                            pids.add(p)
                if not pids:
                    print(f"[Launcher] Puerto {port} disponible.")
                    return
                for pid in pids:
                    print(f"[Launcher] Liberando proceso PID {pid} en puerto {port}")
                    os.system(f'taskkill /PID {pid} /F >nul 2>&1')
                time.sleep(1.5)
            except Exception as e:
                print(f"[Launcher] Error al limpiar puerto {port}: {e}")
                time.sleep(1)
        print(f"[Launcher] Verificación de puerto {port} completada.")


    # Ensure port 9999 is free before binding (helps avoid EXIT code 15 on Windows)
    if os.name == "nt":
        _force_free_port(9999)

    # Diagnostic wrapper: capture full traceback to help debug exit code 15
    try:
        uvicorn.run(app, host="127.0.0.1", port=9999, log_level="info")
    except Exception as e:
        import traceback
        print("ERROR CRÍTICO:", e)
        traceback.print_exc()
        try:
            input("Presiona Enter para salir...")
        except Exception:
            pass
        sys.exit(1)
