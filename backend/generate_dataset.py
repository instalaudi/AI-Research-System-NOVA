"""Script temporal para generar el dataset de NOVA v10.1"""
import asyncio
import sys
import os

# Asegurar que el directorio backend esté en el path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def main():
    from core.database import init_db
    init_db()
    from core.dataset_builder import nova_dataset_builder
    
    print("=" * 60)
    print("  NOVA Dataset Builder v10.1 — Generando dataset...")
    print("=" * 60)
    
    result = await nova_dataset_builder.build_complete_dataset()
    
    print("\n" + "=" * 60)
    print("  RESULTADO FINAL")
    print("=" * 60)
    print(f"  Total de muestras:  {result['total_samples']}")
    print(f"  - Destiladas:       {result['by_source']['distilled']}")
    print(f"  - Conversaciones:   {result['by_source']['conversations']}")
    print(f"  - Investigación:    {result['by_source']['research']}")
    print(f"  - Identidad:        {result['by_source']['identity']}")
    print(f"  Archivo exportado:  {result['export_file']}")
    print(f"  Listo para FT:      {'✅ SÍ' if result['ready_for_finetuning'] else '❌ NO'}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
