import json
import logging
import subprocess
import asyncio
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nova.gws")

class GwsService:
    def __init__(self):
        self.bin_path = "gws" # Asumimos que estará en el PATH

    async def _execute(self, args: List[str]) -> Dict[str, Any]:
        """Ejecuta un comando de gws y retorna el JSON resultante."""
        try:
            full_cmd = [self.bin_path] + args
            # Siempre pedimos JSON para facilitar el procesamiento por NOVA
            if "--json" not in full_cmd and "+agenda" not in full_cmd and "+triage" not in full_cmd:
                # Nota: algunos comandos helper '+' ya devuelven formato legible o JSON
                pass

            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode().strip()
                logger.error(f"Error ejecutando gws: {error_msg}")
                return {"success": False, "error": error_msg}

            output = stdout.decode().strip()
            try:
                # Intentar parsear como JSON si parece JSON
                if output.startswith("{") or output.startswith("["):
                    return {"success": True, "data": json.loads(output)}
                return {"success": True, "raw_output": output}
            except json.JSONDecodeError:
                return {"success": True, "raw_output": output}

        except FileNotFoundError:
            return {
                "success": False, 
                "error": "El binario 'gws' no fue encontrado. Por favor, instala el CLI de Google Workspace."
            }
        except Exception as e:
            logger.error(f"Excepción en GwsService: {e}")
            return {"success": False, "error": str(e)}

    # --- MÉTODOS DE CONVENIENCIA (Helpers +) ---

    async def get_agenda(self, days: int = 1) -> Dict[str, Any]:
        """Obtiene la agenda de los próximos días."""
        return await self._execute(["calendar", "+agenda"])

    async def get_gmail_triage(self) -> Dict[str, Any]:
        """Obtiene un resumen de los correos más importantes."""
        return await self._execute(["gmail", "+triage"])

    async def list_drive_files(self, limit: int = 10) -> Dict[str, Any]:
        """Lista los archivos recientes en Google Drive."""
        params = json.dumps({"pageSize": limit})
        return await self._execute(["drive", "files", "list", "--params", params])

    async def send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Envía un correo electrónico."""
        return await self._execute([
            "gmail", "+send", 
            "--to", to, 
            "--subject", subject, 
            "--body", body
        ])

    async def get_standup_report(self) -> Dict[str, Any]:
        """Genera un reporte de standup (reuniones + tareas)."""
        return await self._execute(["workflow", "+standup-report"])

# Singleton
gws_service = GwsService()
