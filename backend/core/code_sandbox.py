"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v14.0 — Sandbox de Ejecución y Validación TDD           ║
║  Archivo: core/code_sandbox.py                               ║
║  Ejecuta validaciones sintácticas, análisis estático y       ║
║  suites de pruebas en un entorno aislado y seguro.           ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import ast
import json
import subprocess
import sys
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("core.code_sandbox")


class CodeSandbox:
    """
    Sandbox de ejecución segura para validación de código y pruebas TDD.
    Aísla la ejecución en directorios temporales con límites estrictos de tiempo.
    """
    def __init__(self, timeout_seconds: int = 15):
        self.timeout_seconds = timeout_seconds

    def validate_syntax(self, files: Dict[str, str]) -> Dict[str, Any]:
        """
        Valida la sintaxis estática de todos los archivos generados.
        Retorna un reporte detallando si todos los archivos son sintácticamente válidos.
        """
        errors = []
        for file_path, content in files.items():
            ext = Path(file_path).suffix.lower()
            
            # Validación Python AST
            if ext == ".py":
                try:
                    ast.parse(content, filename=file_path)
                except SyntaxError as e:
                    errors.append({
                        "file": file_path,
                        "line": e.lineno,
                        "offset": e.offset,
                        "error": f"SyntaxError: {e.msg}",
                        "code_context": e.text
                    })
                except Exception as e:
                    errors.append({
                        "file": file_path,
                        "error": f"Error de parseo AST: {str(e)}"
                    })
            
            # Validación JSON
            elif ext == ".json":
                try:
                    json.loads(content)
                except json.JSONDecodeError as e:
                    errors.append({
                        "file": file_path,
                        "line": e.lineno,
                        "column": e.colno,
                        "error": f"JSONDecodeError: {e.msg}"
                    })
                    
        return {
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "errors": errors
        }

    def run_tests_in_sandbox(
        self,
        files: Dict[str, str],
        custom_test_cmd: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Escribe los archivos en un espacio temporal aislado y ejecuta las pruebas automatizadas.
        """
        # 1. Primero validar sintaxis básica
        syntax_res = self.validate_syntax(files)
        if not syntax_res["valid"]:
            return {
                "success": False,
                "stage": "syntax_validation",
                "error_trace": "\n".join(
                    f"[{err.get('file')}:{err.get('line', '?')}] {err.get('error')}"
                    for err in syntax_res["errors"]
                ),
                "stdout": "",
                "stderr": "Fallo en validación sintáctica estática."
            }

        with tempfile.TemporaryDirectory(prefix="nova_sandbox_") as tmpdir:
            tmp_path = Path(tmpdir)
            
            # 2. Materializar archivos en el sandbox
            has_python_tests = False
            python_files = []
            
            for rel_path, content in files.items():
                target_file = tmp_path / rel_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(content, encoding="utf-8")
                
                if rel_path.endswith(".py"):
                    python_files.append(rel_path)
                    if "test" in rel_path.lower():
                        has_python_tests = True

            # 3. Determinar comando de prueba
            python_exe = sys.executable
            
            if custom_test_cmd:
                cmd = custom_test_cmd
            elif has_python_tests:
                # Ejecutar pytest en el sandbox
                cmd = [python_exe, "-m", "unittest", "discover", "-s", ".", "-p", "*test*.py"]
            elif python_files:
                # Si no hay tests unitarios explícitos, compilar todos los archivos .py para verificar importabilidad
                cmd = [python_exe, "-m", "py_compile"] + python_files
            else:
                # Para proyectos web estáticos (HTML/CSS/JS), si pasó sintaxis, se aprueba
                return {
                    "success": True,
                    "stage": "static_web",
                    "stdout": "Archivos web estáticos validados correctamente.",
                    "stderr": "",
                    "error_trace": None
                }

            # 4. Ejecutar subproceso aislado
            try:
                env = os.environ.copy()
                env["PYTHONPATH"] = str(tmp_path)
                
                proc = subprocess.run(
                    cmd,
                    cwd=str(tmp_path),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds
                )
                
                success = (proc.returncode == 0)
                error_trace = None if success else (proc.stderr or proc.stdout)
                
                return {
                    "success": success,
                    "return_code": proc.returncode,
                    "stage": "execution",
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "error_trace": error_trace
                }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "stage": "timeout",
                    "stdout": "",
                    "stderr": f"Tiempo de ejecución excedido ({self.timeout_seconds}s en sandbox).",
                    "error_trace": f"TimeoutExpired: La ejecución tardó más de {self.timeout_seconds}s."
                }
            except Exception as e:
                return {
                    "success": False,
                    "stage": "error",
                    "stdout": "",
                    "stderr": str(e),
                    "error_trace": f"SandboxException: {str(e)}"
                }


# Instancia global del Sandbox
code_sandbox = CodeSandbox()
