
import os
import sys
import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro
import time

from core.config import BASE_DIR

class KokoroEngine:
    def __init__(self):
        self.model_path = os.path.join(BASE_DIR, "models", "kokoro", "model.onnx")
        self.voices_path = os.path.join(BASE_DIR, "models", "kokoro", "voices.bin")
        self.kokoro = None
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return True
        try:
            # Auto-detección de espeak-ng en Windows si no está en el PATH
            if os.name == 'nt':
                espeak_path = r"C:\Program Files\eSpeak NG\espeak-ng.exe"
                if os.path.exists(espeak_path):
                    os.environ.setdefault("PHONEMIZER_ESPEAK_PATH", espeak_path)
                    os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", os.path.join(os.path.dirname(espeak_path), "libespeak-ng.dll"))

            if not os.path.exists(self.model_path) or not os.path.exists(self.voices_path):

                print(f"[Kokoro] Model or voices not found")
                return False
            
            print(f"[Kokoro] Loading model from {self.model_path}...")
            start_time = time.time()
            self.kokoro = Kokoro(self.model_path, self.voices_path)
            print(f"[Kokoro] Model loaded in {time.time() - start_time:.2f}s")
            self._initialized = True
            print("[Kokoro] Engine initialized successfully")
            return True
        except Exception as e:
            print(f"[Kokoro] Initialization failed: {e}")
            return False

    def synthesize(self, text, voice_name="af_sarah", output_path="output.wav"):
        if not self._initialized:
            if not self.initialize():
                return None

        try:
            print(f"[Kokoro] Synthesizing text: {text[:50]}...")
            start_time = time.time()
            samples, sample_rate = self.kokoro.create(
                text, 
                voice=voice_name, 
                speed=1.0, 
                lang="es" # Spanish language code for espeak
            )
            print(f"[Kokoro] Synthesis completed in {time.time() - start_time:.2f}s")
            
            sf.write(output_path, samples, sample_rate)
            return output_path
        except Exception as e:
            print(f"[Kokoro] Synthesis failed: {e}")
            return None

    def synthesize_bytes(self, text, voice_name="ef_dora"):
        """
        Genera audio WAV en memoria y devuelve los bytes.
        Seleccionamos 'ef_dora' (Dora) para NOVA por defecto en español.
        """
        if not self._initialized:
            if not self.initialize():
                return None
        try:
            import io
            print(f"[Kokoro] Synthesizing to bytes: {text[:50]}...")
            start_time = time.time()
            samples, sample_rate = self.kokoro.create(
                text, voice=voice_name, speed=1.0, lang="es"
            )
            buffer = io.BytesIO()
            sf.write(buffer, samples, sample_rate, format='WAV')
            buffer.seek(0)
            audio_bytes = buffer.getvalue()
            print(f"[Kokoro] Synthesis completed in {time.time() - start_time:.2f}s ({len(audio_bytes)} bytes)")
            return audio_bytes
        except Exception as e:
            print(f"[Kokoro] Synthesis to bytes failed: {e}")
            return None

kokoro_engine = KokoroEngine()

