
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from core.self_evolution import EvolutionValidator

class SecureFileManager:
    """
    Herramienta de gestión de archivos segura para NOVA.
    Permite leer, escribir y listar archivos dentro del root del proyecto,
    validado por EvolutionValidator para prevenir daños.
    """
    def __init__(self, base_dir: Optional[str] = None):
        # Establecer el directorio base (root del proyecto)
        if base_dir:
            self.base_dir = Path(base_dir).resolve()
        else:
            # Por defecto, asumimos que estamos en backend/core/ y subimos dos niveles
            self.base_dir = Path(__file__).parent.parent.parent.resolve()
        
        self.validator = EvolutionValidator()
        print(f"[FILE_MANAGER] Inicializado en: {self.base_dir}")

    def _safe_path(self, relative_path: str) -> Path:
        """Resuelve el path y verifica que esté dentro de base_dir."""
        target_path = (self.base_dir / relative_path).resolve()
        if not str(target_path).startswith(str(self.base_dir)):
            raise PermissionError(f"Acceso denegado: El path '{relative_path}' está fuera de los límites permitidos.")
        return target_path

    async def list_directory(self, path: str = ".") -> List[str]:
        """Lista archivos y carpetas en un directorio."""
        try:
            target = self._safe_path(path)
            if not target.is_dir():
                return [f"Error: {path} no es un directorio."]
            
            items = os.listdir(target)
            # Filtrar archivos ocultos o sensibles si es necesario
            return [item for item in items if not item.startswith(".")]
        except Exception as e:
            return [f"Error listando {path}: {str(e)}"]

    async def read_file(self, path: str) -> str:
        """Lee el contenido de un archivo."""
        try:
            target = self._safe_path(path)
            if not target.is_file():
                return f"Error: {path} no es un archivo o no existe."
            
            with open(target, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception as e:
            return f"Error leyendo {path}: {str(e)}"

    async def write_file(self, path: str, content: str, reason: str = "Mejora del sistema", backup: bool = True) -> Dict[str, Any]:
        """
        Escribe o edita un archivo de forma ATÓMICA.
        Protege contra corrupciones por cortes de energía (NIAW).
        """
        import shutil
        import tempfile

        try:
            target = self._safe_path(path)
            
            # 1. Preparar 'propuesta' para el Validador
            risk = "low"
            if any(k in path for k in ["config", "main.py", "database.py", "auth.py"]):
                risk = "medium"
            if len(content.strip()) < 10:
                risk = "high"

            proposal = {
                "type": f"file_edit:{path}",
                "description": f"Editando archivo {path}. Razón: {reason}",
                "risk": risk
            }

            if not self.validator.validate_proposal(proposal):
                return {
                    "success": False,
                    "error": f"Acción BLOQUEADA por Guardrails (Riesgo: {risk})."
                }

            # 2. Asegurar que el directorio existe
            os.makedirs(os.path.dirname(target), exist_ok=True)

            # 3. Crear Backup si es requerido y el archivo existe
            if backup and target.exists():
                backup_path = target.with_suffix(target.suffix + ".bak")
                try:
                    shutil.copy2(target, backup_path)
                except Exception as b_err:
                    print(f"[FILE_MANAGER] Warning: No se pudo crear backup de {path}: {b_err}")

            # 4. Escritura ATÓMICA (Pattern: Write -> Flush -> Fsync -> Replace)
            # Usamos un archivo temporal en el mismo directorio que el destino
            # para asegurar que el renombre ocurra en el mismo sistema de archivos.
            temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(target), text=True)
            try:
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Operación atómica de reemplazo (Windows: os.replace)
                os.replace(temp_path, target)
                
            except Exception as e:
                # Limpiar si algo falla antes del reemplazo
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise e

            print(f"[FILE_MANAGER] NIAW: Escritura atómica completada para {path}")
            return {"success": True, "path": path, "size": len(content)}

        except Exception as e:
            return {"success": False, "error": str(e)}

# Instancia global
file_manager = SecureFileManager()
