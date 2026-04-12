import asyncio
import os
import sys
# Set path so python tests run flawlessly with internal imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.developer_agent import developer_agent
from core.project_manager import project_manager

async def test_build():
    print("=== NOVA Developer Agent: Test de Vuelo ===")
    print("Solicitando proyecto: 'Web sencilla de un reloj digital. HTML, CSS y JS'")
    
    try:
        # Llamamos a NOVA
        files = await developer_agent.build_project('Haz una web sencilla de un reloj digital estético. HTML, CSS y JS.')
        
        print("\n[ÉXITO] Archivos generados mágicamente:")
        for file in files.keys():
            print(f"  - {file} ({len(files[file])} bytes)")
        
        # Empaquetamos
        zip_path = project_manager.package_project(files, 'reloj_prueba')
        print(f"\n[ÉXITO] Proyecto empaquetado y listo para descargar en:\n  -> {zip_path}")
        
    except Exception as e:
        print(f"\n[ERROR] El test falló: {e}")

if __name__ == "__main__":
    asyncio.run(test_build())
