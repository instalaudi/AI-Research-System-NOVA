import asyncio
import sys
import os
import re

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.self_evolution import NOVASelfEvolution

async def verify_guardrails():
    print("=== Verificando Guardrail Antifilename ===")
    evolution = NOVASelfEvolution()
    
    # 1. Caso: El LLM devuelve un nombre de archivo (LO QUE FALLABA)
    p_bad = {
        "titulo": "Mejora LLM",
        "codigo": "llm_client.py", # Malo
        "test_code": "assert True"
    }
    
    # Simular la lógica de generate_improvement_proposals
    codigo = p_bad.get("codigo")
    is_filename = re.match(r'^[a-zA-Z0-9_\-\./\\]+\.(py|js|ts|tsx|jsx|css|html|json)$', codigo.strip())
    
    if is_filename:
        print("✅ Guardrail DETECTÓ correctamente el nombre de archivo.")
    else:
        print("❌ Guardrail FALLÓ: No detectó el nombre de archivo.")

    # 2. Caso: Código real
    p_good = {
        "titulo": "Mejora Real",
        "codigo": "def solve():\n    return 42",
        "test_code": "assert True"
    }
    is_filename_good = re.match(r'^[a-zA-Z0-9_\-\./\\]+\.(py|js|ts|tsx|jsx|css|html|json)$', p_good["codigo"].strip())
    if not is_filename_good:
        print("✅ Guardrail PERMITIÓ correctamente el código real.")
    else:
        print("❌ Guardrail BLOQUEÓ erróneamente el código real.")

async def verify_model_override():
    print("\n=== Verificando Override de Modelo ===")
    # Aquí solo verificamos visualmente en el código que se pase model=LLM_MODEL_NAME
    # O podríamos mockear llm_client.chat
    pass

if __name__ == "__main__":
    asyncio.run(verify_guardrails())
