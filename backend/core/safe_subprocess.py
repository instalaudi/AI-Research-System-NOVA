"""
Wrapper seguro para subprocess calls en Windows con manejo de encoding correcto.
Evita UnicodeDecodeError causado por CP1252 vs UTF-8 encoding.

v13.9.5: Wrapper para stdout/stderr encoding en Windows.
"""
import subprocess
import sys
from typing import Any, List, Optional


def run_safe(
    args: List[str],
    *,
    capture_output: bool = True,
    text: bool = True,
    encoding: Optional[str] = None,
    errors: Optional[str] = None,
    **kwargs
) -> subprocess.CompletedProcess:
    """
    Ejecuta subprocess.run() con encoding seguro para Windows.
    
    Por defecto en Windows:
    - encoding: 'latin-1' (puede decodificar cualquier byte sin fallar)
    - errors: 'replace' (caracteres inválidos se reemplazan con ?)
    """
    if sys.platform == 'win32':
        if encoding is None:
            encoding = 'latin-1'  # Seguro para CP1252 de Windows
        if errors is None and text:
            errors = 'replace'
    
    return subprocess.run(
        args,
        capture_output=capture_output,
        text=text,
        encoding=encoding,
        errors=errors,
        **kwargs
    )


def check_output_safe(
    args: List[str],
    *,
    encoding: Optional[str] = None,
    errors: Optional[str] = None,
    **kwargs
) -> str:
    """
    Ejecuta subprocess.check_output() con encoding seguro para Windows.
    """
    if sys.platform == 'win32':
        if encoding is None:
            encoding = 'latin-1'
        if errors is None:
            errors = 'replace'
    
    return subprocess.check_output(
        args,
        text=True,
        encoding=encoding,
        errors=errors,
        **kwargs
    )
