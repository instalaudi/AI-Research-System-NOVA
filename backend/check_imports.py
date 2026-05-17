import time
import sys
import os

# Add backend directory dynamically to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

print("Starting import check...")

def check(name, task, critical=True):
    start = time.time()
    print(f"Importing {name}...", end=" ", flush=True)
    try:
        task()
        print(f"OK ({time.time()-start:.2f}s)")
    except Exception as e:
        print(f"\nFAILED: {e}")
        if name == "whisper":
            print("  [💡 HINT] Si falta whisper, puedes instalarlo con: pip install openai-whisper")
        if critical:
            print(f"CRITICAL ERROR: El módulo '{name}' es requerido para iniciar el sistema.")
            sys.exit(1)

check("fastapi", lambda: __import__("fastapi"), critical=True)
check("whisper", lambda: __import__("whisper"), critical=False)
check("core.orchestrator", lambda: __import__("core.orchestrator"), critical=True)
check("core.task_queue", lambda: __import__("core.task_queue"), critical=True)
check("core.llm_client", lambda: __import__("core.llm_client"), critical=True)
check("core.tts_engine", lambda: __import__("core.tts_engine"), critical=True)
check("core.proactive", lambda: __import__("core.proactive"), critical=True)
check("routers.chat", lambda: __import__("routers.chat"), critical=True)

print("All imports finished successfully.")
