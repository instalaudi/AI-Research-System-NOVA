import subprocess
import os
import re
import shlex
import logging
from typing import Dict, Any

logger = logging.getLogger("core.tool_executor")

# Rutas críticas del sistema (protección contra borrado/escritura)
FORBIDDEN_PATTERNS = [
    r"c:\\windows", 
    r"c:\\program files",
    r"c:\\programdata",
    r"system32",
    r"syswow64",
    r"/etc/",
    r"/usr/bin",
    r"/boot",
]

# Operadores de shell que pueden encadenar o ejecutar comandos arbitrarios
SHELL_META_PATTERN = re.compile(r"[;&|<>`^]|\b(?:&&|\|\||\$\(|\$\{|\$[({])", re.I)

class ToolExecutor:
    """
    Ejecuta comandos de terminal de forma segura, filtrando ataques al SO
    y protegiendo la integridad de NOVA.
    """
    
    def is_safe_command(self, command: str) -> tuple[bool, str]:
        cmd_lower = command.lower()
        
        # 1. Filtro de patrones prohibidos (Comandos destructivos)
        destructive_actions = ["rm ", "del ", "rd ", "rmdir ", "format ", "reg delete", "taskkill", "shutdown", "remove-item", "clear-content", "write-host", "invoke-webrequest"]
        
        # Bloqueo total de rutas críticas para cualquier acceso
        if any(re.search(pattern, cmd_lower, re.I) for pattern in FORBIDDEN_PATTERNS):
            return False, "Acceso directo a rutas del sistema o directorios protegidos no permitido."

        # Bloqueo de comandos específicos peligrosos sin importar la ruta
        for pattern in ["reg add", "net user", "net localgroup", "powershell.*iex", "cmd /c", "bash -c", "sh -c"]:
            if re.search(pattern, cmd_lower, re.I):
                return False, f"Comando administrativo prohibido detectado: {pattern}"

        # Prohibir operadores de shell y concatenación de comandos
        if SHELL_META_PATTERN.search(command):
            return False, "Los operadores de shell y la concatenación de comandos no están permitidos."

        # 2. Protección de la propia carpeta de NOVA
        forbidden_deletions = ["main.py", "backend", "frontend", ".git", "nova"]
        if any(x in cmd_lower for x in destructive_actions):
            if any(target in cmd_lower for target in forbidden_deletions):
                return False, "Intento de modificar o eliminar archivos núcleo de NOVA."
                
        return True, ""

    async def execute_terminal(self, command: str) -> Dict[str, Any]:
        """Ejecuta un comando en la shell del sistema y devuelve stdout/stderr."""
        is_safe, reason = self.is_safe_command(command)
        if not is_safe:
            return {
                "status": "blocked",
                "stdout": "",
                "stderr": f"BLOQUEO DE SEGURIDAD: {reason}",
                "exit_code": 1
            }
            
        try:
            args = shlex.split(command, posix=(os.name != "nt"))
            if not args:
                return {
                    "status": "blocked",
                    "stdout": "",
                    "stderr": "Comando vacío o no válido.",
                    "exit_code": 1
                }

            process = await asyncio.to_thread(
                subprocess.run,
                args,
                shell=False,
                capture_output=True,
                text=True,
                errors="replace", # Evita crasheos por caracteres extraños en Windows (cp1252)
                timeout=30 # Timeout de seguridad
            )
            
            return {
                "status": "success" if process.returncode == 0 else "error",
                "stdout": process.stdout,
                "stderr": process.stderr,
                "exit_code": process.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "stdout": "",
                "stderr": "Error: El comando excedió el tiempo límite de 30 segundos.",
                "exit_code": 124
            }
        except Exception as e:
            return {
                "status": "exception",
                "stdout": "",
                "stderr": f"Error inesperado ejecutando comando: {str(e)}",
                "exit_code": 1
            }

import asyncio # Necesario para to_thread
tool_executor = ToolExecutor()
