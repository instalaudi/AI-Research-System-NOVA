
import os
import sys
sys.path.append(os.path.join(os.getcwd(), "backend"))
from core.kokoro_engine import kokoro_engine

print("Initializing Kokoro...")
if kokoro_engine.initialize():
    print("Kokoro initialized successfully!")
    print("Testing synthesis...")
    res = kokoro_engine.synthesize("Hola, soy NOVA. Probando el motor Kokoro en español.", voice_name="af_sarah", output_path="kokoro_test.wav")
    if res:
        print(f"Synthesis successful: {res}")
    else:
        print("Synthesis failed.")
else:
    print("Kokoro initialization failed.")
