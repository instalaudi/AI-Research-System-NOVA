import os
import shutil
import asyncio
import logging
from typing import List, Optional
from pathlib import Path

from core.logger import agent_logger
from core.tts_engine import nova_voice
from services.system_service import system_service

logger = logging.getLogger("core.integrity")

# ── Listado de Archivos Críticos para el funcionamiento de NOVA ───
CRITICAL_FILES = [
    # Core
    "backend/main.py",
    "backend/core/config.py",
    "backend/core/database.py",
    "backend/core/distillation.py",
    "backend/core/self_evolution.py",
    "backend/core/orchestrator.py",
    "backend/core/task_queue.py",
    # Data / State
    "backend/data/nova_proactive_state.json",
    "backend/data/nova_evolution_state.json",
]

async def check_system_integrity():
    """
    Escanea archivos críticos en busca de corrupción tras el arranque.
    Detecta archivos vacíos (0 bytes) o con bytes nulos.
    Autorepara desde .bak si están disponibles.
    """
    print("[INTEGRITY] Iniciando escaneo de salud del sistema...")
    corrupted_found = []
    
    # Directorio base del proyecto
    base_dir = Path(__file__).parent.parent.parent.resolve()
    
    for rel_path in CRITICAL_FILES:
        target = base_dir / rel_path
        
        if not target.exists():
            continue
            
        is_corrupted = False
        reason = ""
        
        # 1. Verificar si está vacío (0 bytes)
        if target.stat().st_size == 0:
            is_corrupted = True
            reason = "Tamaño 0 bytes"
            
        # 2. Verificar bytes nulos (solo si no es gigantesco)
        if not is_corrupted and target.stat().st_size < 5 * 1024 * 1024: # < 5MB
            try:
                with open(target, 'rb') as f:
                    content = f.read()
                    if b'\x00' in content:
                        is_corrupted = True
                        reason = "Contiene bytes nulos (null bytes)"
            except Exception as e:
                print(f"[INTEGRITY] Error leyendo {rel_path}: {e}")
                
        if is_corrupted:
            print(f"[INTEGRITY] ⚠️ CORRUPCIÓN DETECTADA en {rel_path}: {reason}")
            success = await _attempt_repair(target, rel_path, reason)
            if success:
                corrupted_found.append(rel_path)
                # v11.0: Persistencia de fallo en Dashboard
                await system_service.log_system_failure(
                    type='CORRUPTION',
                    description=f'Archivo reparado automáticamente: {rel_path} ({reason})',
                    severity='critical'
                )

    if corrupted_found:
        msg = f"Atención Juan Ramón. He detectado y reparado archivos corruptos en {', '.join(corrupted_found)}. El sistema ya es estable."
        await agent_logger.log("IntegrityGuard", f"REPARACIÓN AUTÓNOMA: Se restauraron {len(corrupted_found)} archivos.")
        
        # Notificar por voz si el motor está listo
        try:
            # No esperamos el audio aquí para no bloquear el arranque
            # pero intentamos disparar la síntesis.
            asyncio.create_task(_notify_by_voice(msg))
        except:
            pass
    else:
        print("[INTEGRITY] ✅ Todos los archivos críticos están íntegros.")

async def _attempt_repair(target: Path, rel_path: str, reason: str) -> bool:
    """Intenta restaurar un archivo desde su copia .bak."""
    bak_path = target.with_suffix(target.suffix + ".bak")
    
    if bak_path.exists() and bak_path.stat().st_size > 0:
        try:
            # Verificar si el backup también está corrupto
            with open(bak_path, 'rb') as f:
                if b'\x00' in f.read():
                    print(f"[INTEGRITY] ❌ Backup de {rel_path} también está corrupto.")
                    return False
            
            # Restaurar
            shutil.copy2(bak_path, target)
            print(f"[INTEGRITY] ✅ Archivo {rel_path} RESTAURADO con éxito desde backup.")
            return True
        except Exception as e:
            print(f"[INTEGRITY] ❌ Falló la restauración de {rel_path}: {e}")
    else:
        print(f"[INTEGRITY] ❌ No se encontró un backup válido (.bak) para {rel_path}.")
        
    return False

async def _notify_by_voice(message: str):
    """Espera a que TTS esté listo y emite el aviso."""
    # Esperar un poco a que el motor TTS cargue (usualmente 10-20s en lifespan)
    for _ in range(30):
        if nova_voice._ready:
            await nova_voice.synthesize(message)
            return
        await asyncio.sleep(2)
