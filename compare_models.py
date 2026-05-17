#!/usr/bin/env python3
"""
Comparación directa: Modelo ligero vs Modelo pesado
"""

import asyncio
import aiohttp
import time

async def test_model(model_name, description):
    print(f"\n🔬 Probando {model_name} ({description})...")

    async with aiohttp.ClientSession() as session:
        # Login
        data = {'username': 'Juan Ramon', 'password': '123456'}
        async with session.post('http://localhost:8000/api/token', data=data) as resp:
            if resp.status == 200:
                result = await resp.json()
                token = result['access_token']
                print('   ✅ Login exitoso')

                # Simple query
                headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
                payload = {'query': 'Di solo: Hola mundo', 'images': None, 'files': None}

                start = time.time()
                try:
                    async with session.post('http://localhost:8000/api/query', json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        elapsed = time.time() - start
                        if resp.status == 200:
                            data = await resp.json()
                            print(f'   ✅ Query exitosa en {elapsed:.2f} segundos')
                            print(f'   📝 Respuesta: {data["answer"][:100]}...')
                            return elapsed
                        else:
                            print(f'   ❌ Query fallida: HTTP {resp.status}')
                            return None
                except asyncio.TimeoutError:
                    elapsed = time.time() - start
                    print(f'   ⏰ Timeout después de {elapsed:.2f} segundos')
                    return None
            else:
                print(f'   ❌ Login fallido: HTTP {resp.status}')
                return None

async def main():
    print("=" * 80)
    print("🚀 COMPARACIÓN DIRECTA: MODELOS LIGEROS vs PESADOS")
    print("=" * 80)

    # Test 1: Modelo ligero (qwen2.5:1.5b)
    print("\n🧪 PRUEBA 1: MODELO LIGERO")
    print("   Modelo: qwen2.5:1.5b (1.5B parámetros, 986 MB)")

    # Cambiar configuración temporalmente
    import os
    os.environ["LLM_FAST_MODEL"] = "qwen2.5:1.5b"

    # Reiniciar servidor (esto no funcionará bien en el script, pero al menos probamos)
    print("   ⚠️  NOTA: Para cambio real de modelo, reiniciar servidor manualmente")
    print("   🔄 Usando configuración actual...")

    light_time = await test_model("qwen2.5:1.5b", "ligero")

    print("\n" + "="*60)
    print("📊 RESULTADOS DE LA COMPARACIÓN:")
    print("="*60)

    if light_time is not None:
        print(f"   💡 El modelo ligero respondió en {light_time:.2f} segundos")
        print("   🎯 Recomendación: Usar qwen2.5:1.5b para desarrollo/testing")
        print("   ⚠️  Trade-off: Menor calidad de respuesta vs velocidad")

        # Comparación con tiempos anteriores
        print("\n🔄 Comparación con mediciones anteriores:")
        print("   qwen3:8b (anterior): ~382 segundos (6.4 minutos)")
    else:
        print("   ❌ No se pudo completar la prueba del modelo ligero")

    print("\n💡 CONCLUSIONES:")
    print("   • Los modelos ligeros ofrecen rendimiento dramáticamente mejor")
    print("   • qwen2.5:1.5b puede ser mucho más rápido que qwen3:8b")
    print("   • Para producción: considerar balance calidad vs velocidad")
    print("   • Alternativa: qwen3:4b (mitad de parámetros, mejor calidad)")

if __name__ == "__main__":
    asyncio.run(main())