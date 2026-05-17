import requests
import time
import psutil
import os

def get_ollama_stats():
    try:
        # Get loaded models
        r = requests.get("http://localhost:11434/api/ps", timeout=5)
        if r.status_code == 200:
            models = r.json().get("models", [])
            return len(models), sum(m.get("size", 0) for m in models) / (1024**3)  # GB
    except:
        pass
    return 0, 0

def get_system_memory():
    mem = psutil.virtual_memory()
    return mem.percent, mem.used / (1024**3), mem.total / (1024**3)

def monitor_ollama():
    print("=== MONITOREO DE OLLAMA ===")
    print("Presiona Ctrl+C para detener")
    print()

    while True:
        # Ollama stats
        num_models, total_size = get_ollama_stats()

        # System memory
        mem_percent, mem_used, mem_total = get_system_memory()

        # Ollama processes
        ollama_procs = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                if 'ollama' in proc.info['name'].lower():
                    mem_mb = proc.info['memory_info'].rss / (1024**2)
                    ollama_procs.append((proc.info['pid'], mem_mb))
            except:
                pass

        print(f"[{time.strftime('%H:%M:%S')}] Modelos cargados: {num_models} | Tamaño total: {total_size:.1f}GB")
        print(f"  Memoria sistema: {mem_used:.1f}GB / {mem_total:.1f}GB ({mem_percent:.1f}%)")
        print(f"  Procesos Ollama: {len(ollama_procs)}")

        for pid, mem_mb in sorted(ollama_procs, key=lambda x: x[1], reverse=True)[:3]:
            print(f"    PID {pid}: {mem_mb:.0f}MB")

        # Check for high memory usage
        if mem_percent > 85:
            print("  ⚠️  MEMORIA ALTA!")
        if total_size > 8:
            print("  ⚠️  MODELOS GRANDES CARGADOS!")

        print("-" * 50)
        time.sleep(10)

if __name__ == "__main__":
    monitor_ollama()