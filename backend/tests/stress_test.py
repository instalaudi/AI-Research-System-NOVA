import asyncio
import httpx
import time
import json
import statistics
from typing import List, Dict

BASE_URL = "http://localhost:8000"
USER_CREDENTIALS = {"username": "admin", "password": "password123"} # Mock or existing

async def fetch_token():
    async with httpx.AsyncClient() as client:
        try:
            # Try to register first just in case
            await client.post(f"{BASE_URL}/register", json={
                "username": USER_CREDENTIALS["username"],
                "password": USER_CREDENTIALS["password"],
                "email": "test@nova.ai"
            })
            
            # Login
            resp = await client.post(f"{BASE_URL}/token", data=USER_CREDENTIALS)
            if resp.status_code == 200:
                return resp.json()["access_token"]
        except Exception as e:
            print(f"Error getting token: {e}")
    return None

async def stress_query_endpoint(token: str, query: str, request_id: int):
    headers = {"Authorization": f"Bearer {token}", "X-Request-ID": f"stress-test-{request_id}"}
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{BASE_URL}/query", 
                json={"query": query}, 
                headers=headers
            )
            latency = (time.time() - start) * 1000
            return {
                "id": request_id,
                "status": resp.status_code,
                "latency": latency,
                "success": resp.status_code == 200
            }
    except Exception as e:
        return {"id": request_id, "status": "Error", "latency": 0, "success": False, "error": str(e)}

async def stress_health_endpoint():
    start = time.time()
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/health")
        latency = (time.time() - start) * 1000
        return {"status": resp.status_code, "latency": latency}

async def run_stress_test(concurrency: int = 10):
    print(f"\n🚀 Iniciando Prueba de Estrés: {concurrency} peticiones concurrentes")
    token = await fetch_token()
    if not token:
        print("❌ Fallo al obtener el token. ¿Está el servidor corriendo?")
        return

    # Phase 1: Heavy Query load
    queries = [
        "¿Cuál es el estado del proyecto NOVA?",
        "Explica la arquitectura de servicios que implementamos.",
        "¿Cómo funciona el request_id?",
        "Genera un resumen de los últimos logs.",
        "¿Qué es la auto-evolución?"
    ] * (concurrency // 5 + 1)
    
    tasks = []
    for i in range(concurrency):
        tasks.append(stress_query_endpoint(token, queries[i], i))
    
    print(f"[*] Enviando {concurrency} queries al motor cognitivo...")
    results = await asyncio.gather(*tasks)
    
    # Phase 2: Monitoring Health during load
    health = await stress_health_endpoint()
    
    # Results Analysis
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    latencies = [r["latency"] for r in successes]
    
    print("\n📊 RESULTADOS")
    print(f"----------------------------------------")
    print(f"Total Peticiones: {concurrency}")
    print(f"Éxitos:           {len(successes)} ✅")
    print(f"Fallos:           {len(failures)} ❌")
    
    if latencies:
        print(f"Latencia Media:   {statistics.mean(latencies):.2f} ms")
        print(f"Latencia P95:     {statistics.quantiles(latencies, n=20)[18]:.2f} ms")
    
    print(f"Health Status:    {health['status']} (Latencia: {health['latency']:.2f} ms)")
    print(f"----------------------------------------\n")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_stress_test(concurrency=20))
