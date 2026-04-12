"""
Script de benchmark para medir latencia real de Ollama.
Ejecutar ANTES y DESPUÉS del reinicio de NOVA para comparar.

Uso:
    cd backend
    python ../scripts/benchmark_ollama.py

No requiere que NOVA esté corriendo — habla directamente con Ollama.
"""

import httpx
import time
import statistics
import json
import sys

OLLAMA_BASE = "http://localhost:11434"
MODELS_TO_TEST = ["qwen2.5:1.5b"]
NUM_RUNS = 3

TEST_PROMPT = "Responde en una sola frase: ¿Qué es un grafo de conocimiento?"
NUM_CTX_VALUES = [4096, 2048]  # Comparar ambos

def measure(model: str, num_ctx: int) -> list[float]:
    """Mide NUM_RUNS llamadas y devuelve lista de latencias en segundos."""
    latencies = []
    url = f"{OLLAMA_BASE}/api/chat"
    for i in range(NUM_RUNS):
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": TEST_PROMPT}],
            "stream": False,
            "options": {
                "num_ctx":     num_ctx,
                "num_predict": 128,
                "num_thread":  8,
                "temperature": 0.1,
            }
        }
        t0 = time.time()
        try:
            r = httpx.post(url, json=payload, timeout=180.0)
            r.raise_for_status()
            elapsed = time.time() - t0
            latencies.append(elapsed)
            tokens = r.json().get("eval_count", "?")
            tps = int(tokens) / elapsed if isinstance(tokens, int) else "?"
            print(f"  Run {i+1}: {elapsed:.1f}s | tokens={tokens} | {tps:.1f} t/s" if isinstance(tps, float) else f"  Run {i+1}: {elapsed:.1f}s")
        except Exception as e:
            print(f"  Run {i+1}: ERROR — {e}")
    return latencies

def main():
    print(f"\n{'='*60}")
    print("  NOVA — Benchmark de Latencia Ollama")
    print(f"{'='*60}")

    # Verificar que Ollama está disponible
    try:
        r = httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=5.0)
        r.raise_for_status()
        modelos = [m["name"] for m in r.json().get("models", [])]
        print(f"\n✅ Ollama disponible. Modelos cargados: {', '.join(modelos[:5])}\n")
    except Exception as e:
        print(f"❌ Ollama no disponible: {e}")
        sys.exit(1)

    results = {}
    for model in MODELS_TO_TEST:
        if not any(model in m for m in modelos):
            print(f"⚠️  Modelo '{model}' no encontrado. Saltando...\n")
            continue

        for ctx in NUM_CTX_VALUES:
            label = f"{model} (num_ctx={ctx})"
            print(f"\n🧪 Testeando: {label}")
            lats = measure(model, ctx)
            if lats:
                avg = statistics.mean(lats)
                p95 = sorted(lats)[int(len(lats)*0.95)-1] if len(lats) > 1 else lats[0]
                results[label] = {"avg": avg, "p95": p95, "samples": len(lats)}
                print(f"  → Avg: {avg:.1f}s | P95: {p95:.1f}s")

    # Resumen comparativo
    print(f"\n{'='*60}")
    print("  RESUMEN COMPARATIVO")
    print(f"{'='*60}")
    print(f"{'Configuración':<35} {'Avg (s)':>10} {'P95 (s)':>10}")
    print("-"*55)
    for label, r in results.items():
        print(f"{label:<35} {r['avg']:>10.1f} {r['p95']:>10.1f}")

    # Recomendación automática
    if len(results) >= 2:
        vals = list(results.values())
        if vals[1]["avg"] < vals[0]["avg"]:
            mejora = (1 - vals[1]["avg"] / vals[0]["avg"]) * 100
            print(f"\n✅ Reducir num_ctx mejora la latencia en ~{mejora:.0f}%")
        else:
            print(f"\n⚠️  num_ctx no impacta significativamente la latencia")

    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
