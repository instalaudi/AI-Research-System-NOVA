import asyncio
import os
import sys

# Aadir el directorio backend al path para poder importar los mdulos
sys.path.append(os.path.join(os.getcwd(), "backend"))

from core.task_queue import task_queue
from core.orchestrator import orchestrator
from core.database import init_db

async def main():
    print("Iniciando recuperacin forzada de tareas...")
    init_db()
    
    # Simular el arranque para que los workers estn listos (aunque no ejecutaremos el bucle principal de FastAPI)
    # Solo necesitamos que recovery_scan inyecte las tareas en Redis
    await task_queue.recovery_scan(orchestrator.handle_task)
    print("Escaneo de recuperacin completado. Las tareas pendientes han sido re-encoladas.")

if __name__ == "__main__":
    asyncio.run(main())
