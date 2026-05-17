import asyncio
import os
import sys

# Add project paths to import core modules dynamically
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from core.task_queue import task_queue
from core.database import init_db

async def main():
    print("Iniciando recuperación forzada de tareas...")
    init_db()
    
    # Simular el arranque para que los workers estén listos.
    # El método recovery_scan detecta trabajos pendientes y los re-encola en Redis de forma autónoma.
    await task_queue.recovery_scan()
    print("Escaneo de recuperacin completado. Las tareas pendientes han sido re-encoladas.")

if __name__ == "__main__":
    asyncio.run(main())
