"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v10.0 — Motor de Voz (TTS)                            ║
║  Archivo: core/tts_engine.py                                 ║
║  NOVA habla con su propia voz usando Piper TTS               ║
║  Rápido en CPU, voz natural en español                       ║
╚══════════════════════════════════════════════════════════════╝

INSTALACIÓN (ejecutar una sola vez):
    pip install piper-tts --break-system-packages

VOCES DISPONIBLES EN ESPAÑOL:
    es_MX-claude-high       ← Recomendada (mexicano, alta calidad)
    es_ES-davefx-medium     ← Española
    es_MX-ald-medium        ← Mexicano alternativo

Las voces se descargan automáticamente la primera vez.
"""

import os
import io
import wave
import tempfile
import asyncio
import hashlib
import concurrent.futures
from pathlib import Path
from typing import Optional, List, AsyncGenerator, Dict, Any

from core.kokoro_engine import kokoro_engine

from core.logging_config import get_logger

logger = get_logger("core.tts")


from core.config import DATA_DIR

# ── Directorio de caché de voces ─────────────────────────────────
VOICE_DIR   = Path(DATA_DIR) / "tts_voices"
CACHE_DIR   = Path(DATA_DIR) / "tts_cache"
VOICE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Voz por defecto de NOVA ───────────────────────────────────────
DEFAULT_VOICE   = os.getenv("NOVA_VOICE", "ef_dora")
DEFAULT_SPEAKER = 0
DEFAULT_SPEED   = float(os.getenv("NOVA_VOICE_SPEED", "1.0"))

# ── Voces Curadas Edge-TTS (Nube) ─────────────────────────────────
EDGE_VOICES = [
    "es-MX-DaliaNeural",  # Mujer (México) - Estilo Alexa
    "es-ES-ElviraNeural", # Mujer (España)
    "es-MX-JorgeNeural",  # Hombre (México)
    "es-ES-AlvaroNeural", # Hombre (España)
]

# ── Voces Curadas Kokoro (Local Neuronal) ─────────────────────────
KOKORO_VOICES = [
    "ef_dora",    # Femenina (Española) - Excelente
    "em_alex",    # Masculina (Española) - Excelente
    "af_sarah",   # Femenina (Inglés)
    "af_bella",   # Femenina (Inglés)
    "am_adam",    # Masculina (Inglés)
    "em_santa",   # Masculina (Española - Navideña/Festiva)
]

# ── Process Pool for Kokoro (Ryzen 7 Optimization) ───────────────
_kokoro_pool = None

def _get_kokoro_pool():
    global _kokoro_pool
    if _kokoro_pool is None:
        # max_workers=1 ensures we don't spawn multiple heavy 1.5GB processes
        _kokoro_pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=1,
            initializer=_kokoro_worker_init
        )
    return _kokoro_pool

def _kokoro_worker_init():
    """Reducir la prioridad del proceso worker para no ahogar al LLM."""
    try:
        import psutil
        p = psutil.Process()
        if os.name == 'nt':
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            try:
                p.nice(10)
            except Exception:
                pass
    except Exception:
        pass


def _kokoro_synthesis_worker(text: str, voice_name: str) -> Optional[bytes]:

    """Worker function that runs in a separate process to avoid GIL/CPU contention."""
    try:
        from core.kokoro_engine import kokoro_engine
        if not kokoro_engine._initialized:
            kokoro_engine.initialize()
        return kokoro_engine.synthesize_bytes(text, voice_name)
    except Exception as e:
        print(f"[TTS-Worker] Error in Kokoro process: {e}")
        return None


class NOVAVoiceEngine:
    """
    Motor de síntesis de voz de NOVA.
    Usa Piper TTS para generar audio natural en español.
    NOVA habla — no solo responde texto.
    """

    def __init__(self):
        self._voice     = None
        self._model_name = DEFAULT_VOICE
        self._ready     = False
        self._loading   = False
        self._use_cache = True
        self.engine     = None  # "kokoro", "piper", "edge-tts", "legacy"


    # ══════════════════════════════════════════════════════════
    #  INICIALIZACIÓN
    # ══════════════════════════════════════════════════════════

    async def initialize(self, voice_name: Optional[str] = None) -> bool:
        """Inicializa el motor de voz de NOVA, priorizando Kokoro."""
        if self._ready:
            return True
        if self._loading:
            # Esperar si ya está cargando
            for _ in range(30):
                await asyncio.sleep(1)
                if self._ready:
                    return True
            return False

        self._loading = True
        
        try:
            voice = voice_name or self._model_name
            
            # 1. Si es voz de Kokoro, inicializar Kokoro
            kokoro_prefixes = ("af_", "am_", "bf_", "bm_", "ef_", "em_", "ff_", "if_", "im_", "jf_", "jm_", "pf_", "pm_", "zf_", "zm_")
            if voice.startswith(kokoro_prefixes):
                if kokoro_engine.initialize():
                    self.engine = "kokoro"
                    self._model_name = voice
                    self._ready = True
                    print(f"[OK] [TTS] Voz neuronal Kokoro '{voice}' activada")
                    return True

            # 2. Si es una voz Neural de Edge-TTS
            if voice.endswith("Neural"):
                self.engine = "edge-tts"
                self._model_name = voice
                self._ready = True
                print(f"[TTS] Voz Edge-TTS '{voice}' lista")
                return True

            # 3. Fallback a Piper (anterior)
            print(f"[TTS] Cargando voz de NOVA: {voice}...")
            # Importar piper
            from piper.voice import PiperVoice  # type: ignore

            # Buscar modelo descargado localmente
            model_path = VOICE_DIR / f"{voice}.onnx"
            config_path = VOICE_DIR / f"{voice}.onnx.json"

            if not model_path.exists():
                print(f"[TTS] Descargando voz {voice}...")
                await self._download_voice(voice)

            if model_path.exists():
                self._voice = PiperVoice.load(
                    str(model_path),
                    config_path=str(config_path) if config_path.exists() else None,
                    use_cuda=False  # CPU mode
                )
                self._model_name = voice
                self._ready = True
                self.engine = "piper"
                print(f"[TTS] Voz de NOVA lista (Piper): {voice}")
                return True
            else:
                print(f"[TTS] No se pudo cargar la voz {voice}")
                self.engine = "legacy"
                self._ready = True
                return False

        except ImportError:
            print("[TTS] Piper no instalado. Ejecuta: pip install piper-tts")
            print("[TTS] Usando TTS de fallback (espeak)...")
            self._ready = True  # Usar fallback
            return True
        except Exception as e:
            print(f"[TTS] Error inicializando: {e}")
            return False
        finally:
            self._loading = False

        return False

    async def _download_voice(self, voice_name: str):
        """Descarga una voz de Piper automáticamente."""
        try:
            import httpx  # type: ignore
            base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

            # Parse voice name: lang_region-speaker-quality (e.g., es_MX-claude-high)
            parts = voice_name.split("-")
            lang_region = parts[0] if len(parts) > 0 else "es_ES"
            speaker     = parts[1] if len(parts) > 1 else "default"
            quality     = parts[2] if len(parts) > 2 else "medium"
            lang_code   = lang_region.split("_")[0]

            lang_path = f"{lang_code}/{lang_region}/{speaker}/{quality}"

            urls = [
                f"{base_url}/{lang_path}/{voice_name}.onnx",
                f"{base_url}/{lang_path}/{voice_name}.onnx.json",
            ]

            async with httpx.AsyncClient(timeout=900.0) as client:
                for url in urls:
                    fname = url.split("/")[-1]
                    dest  = VOICE_DIR / fname
                    if dest.exists():
                        continue
                    print(f"[TTS] Descargando {fname}...")
                    r = await client.get(url, follow_redirects=True)
                    if r.status_code == 200:
                        dest.write_bytes(r.content)
                        print(f"[TTS] {fname} descargado ({len(r.content)//1024}KB)")
                    else:
                        print(f"[TTS] Error descargando {fname}: HTTP {r.status_code} desde {url}")

        except Exception as e:
            print(f"[TTS] Error descargando voz: {e}")

    # ══════════════════════════════════════════════════════════
    #  SÍNTESIS DE VOZ
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _segment_text_for_streaming(text: str) -> List[str]:
        """
        Segmenta texto en cláusulas y oraciones fonéticamente naturales para baja latencia.
        Prioriza divisiones por '.', '!', '?', '\n', ';', ':', ',' para emitir el primer
        bloque de audio en <300ms.
        """
        if not text:
            return []
        
        import re
        cleaned = re.sub(r'\s+', ' ', text.strip())
        raw_parts = re.split(r'([\.\!\?\n]+|[\,\;\:]\s+)', cleaned)
        
        segments = []
        current = ""
        
        for part in raw_parts:
            if not part:
                continue
            current += part
            if any(current.rstrip().endswith(p) for p in ['.', '!', '?', ';', ':']) or (',' in current and len(current) >= 40):
                if len(current.strip()) >= 5:
                    segments.append(current.strip())
                current = ""
            elif len(current) >= 120:
                segments.append(current.strip())
                current = ""
                
        if current.strip():
            segments.append(current.strip())
            
        return segments if segments else [cleaned]

    async def synthesize_stream(
        self,
        text: str,
        speed: Optional[float] = None,
        speaker: int = DEFAULT_SPEAKER
    ):
        """
        Generador asíncrono que sintetiza y emite fragmentos de audio en streaming.
        Permite reproducción instantánea en el frontend sin esperar la respuesta completa.
        """
        if not text or not text.strip():
            return
            
        segments = self._segment_text_for_streaming(text)
        for segment in segments:
            audio_chunk = await self.synthesize(segment, speed=speed, speaker=speaker)
            if audio_chunk:
                yield audio_chunk

    async def synthesize(
        self,
        text:     str,
        speed:    Optional[float] = None,
        speaker:  int   = DEFAULT_SPEAKER,
    ) -> Optional[bytes]:
        """
        Convierte texto a audio WAV.
        Si el texto es largo, lo divide en fragmentos para mantener la calidad.
        """

        if not text or not text.strip():
            return None

        # Limpiar el texto para TTS
        clean_text = self._clean_for_tts(text)
        if not clean_text:
            return None

        # Aumentamos agresivamente el límite de 280 a 3000 para que NOVA lea reportes enteros.
        if len(clean_text) > 3000:
            # Truncar en el último espacio antes del límite para no cortar palabras
            truncated = clean_text[:3000].rsplit(" ", 1)[0]
            clean_text = truncated + "."
            print(f"[TTS] Texto truncado para voz: {len(clean_text)} chars (era {len(text)} chars)")

        # Verificar caché
        cache_key  = hashlib.md5(f"{clean_text}{speed}{speaker}{self._model_name}{self.engine}".encode()).hexdigest()
        cache_file = CACHE_DIR / f"{cache_key}.wav"
        if self._use_cache and cache_file.exists():
            return cache_file.read_bytes()

        # 1. Usar Kokoro si está disponible (Procesamiento en Proceso Separado)
        if self.engine == "kokoro":
            try:
                loop = asyncio.get_running_loop()
                pool = _get_kokoro_pool()
                audio_bytes = await loop.run_in_executor(
                    pool, _kokoro_synthesis_worker, clean_text, self._model_name
                )
                if audio_bytes and self._use_cache:
                    cache_file.write_bytes(audio_bytes)
                return audio_bytes
            except Exception as e:
                logger.error(f"[TTS] Error en executor de Kokoro: {e}")
                # Fallback a Piper si el proceso falla
                self.engine = "piper"


        # 2. Verificar si es una voz Neural (Edge TTS)
        if self._model_name.endswith("Neural"):
            audio_bytes = await self._synthesize_edge_tts(clean_text, self._model_name)
            if audio_bytes and self._use_cache:
                cache_file.write_bytes(audio_bytes)
            return audio_bytes

        # 3. Si no es Kokoro ni Neural, asegurar que Piper/Legacy esté listo
        if not self._ready:
            ok = await self.initialize()
            if not ok:
                return await self._fallback_tts(clean_text)


        # Decidir si procesamos todo de una vez o por fragmentos
        # Si el texto es largo (>250 chars), usamos fragmentos para evitar degradación de voz
        if len(clean_text) > 250:
            chunks = self._split_sentences(clean_text)
            print(f"[TTS] Procesando texto largo en {len(chunks)} fragmentos...")
        else:
            chunks = [clean_text]

        # Síntesis con Piper (en thread separado)
        audio_bytes = await asyncio.to_thread( # type: ignore
            self._synthesize_chunks_sync,
            chunks,
            speed or DEFAULT_SPEED,
            speaker
        )

        # Guardar en caché
        if audio_bytes and self._use_cache:
            cache_file.write_bytes(audio_bytes)

        return audio_bytes

    def _synthesize_chunks_sync(
        self,
        chunks:  list[str],
        speed:   float,
        speaker: int
    ) -> Optional[bytes]:
        """Síntesis de múltiples fragmentos en un solo WAV."""
        try:
            voice = self._voice
            if voice is None:
                return None

            # Manejo de múltiples hablantes si el modelo lo soporta
            kwargs = {}
            if getattr(voice.config, "num_speakers", 1) > 1:
                kwargs["speaker_id"] = speaker

            buf = io.BytesIO()
            # Definir parámetros de audio (Piper por defecto usa 22050Hz, 16bit, mono)
            sample_rate = getattr(voice.config, "sample_rate", 22050)
            
            with wave.open(buf, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                
                # Silencio de 150ms entre fragmentos (en bytes: rate * channels * width * duration)
                silence_frames = int(sample_rate * 0.15)
                silence_bytes = b'\x00' * (silence_frames * 2)

                for i, chunk in enumerate(chunks):
                    if not chunk.strip():
                        continue
                    
                    # Sintetizar fragmento en un buffer temporal
                    chunk_buf = io.BytesIO()
                    with wave.open(chunk_buf, "wb") as chunk_wav:
                        chunk_wav.setnchannels(1)
                        chunk_wav.setsampwidth(2)
                        chunk_wav.setframerate(sample_rate)
                        voice.synthesize_wav(chunk, chunk_wav, **kwargs)
                    
                    # Extraer solo los frames usando el módulo wave
                    chunk_buf.seek(0)
                    with wave.open(chunk_buf, 'rb') as read_chunk:
                        pcm_data = read_chunk.readframes(read_chunk.getnframes())
                    wav_file.writeframes(pcm_data)
                    
                    # Añadir pequeña pausa si no es el último fragmento
                    if i < len(chunks) - 1:
                        wav_file.writeframes(silence_bytes)

            return buf.getvalue()

        except Exception as e:
            print(f"[TTS] Error en síntesis de fragmentos: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _synthesize_edge_tts(self, text: str, voice: str) -> Optional[bytes]:
        """Síntesis usando Microsoft Edge TTS (Requiere Internet)."""
        try:
            import edge_tts  # type: ignore
            # Edge-TTS output is MP3, the frontend <audio> element handles it perfectly
            communicate = edge_tts.Communicate(text, voice)
            
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
                
            await communicate.save(tmp_path)
            
            if os.path.exists(tmp_path):
                audio = Path(tmp_path).read_bytes()
                os.unlink(tmp_path)
                return audio
            return None
        except ImportError:
            print("[TTS] [!] edge-tts no instalado. Ejecuta: pip install edge-tts")
            return None
        except Exception as e:
            print(f"[TTS] Error en Edge-TTS: {e}")
            return None

    async def _fallback_tts(self, text: str) -> Optional[bytes]:
        """
        Fallback usando espeak si Piper no está disponible.
        Menos natural pero funcional.
        """
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            import subprocess
            proc = await asyncio.create_subprocess_exec(
                "espeak-ng",
                "-v", "es",
                "-s", "140",    # velocidad
                "-a", "180",    # amplitud
                "-w", tmp_path,
                text[:500],     # type: ignore
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                proc.kill()
                print(f"[TTS] espeak-ng timeout")
                return None
            except Exception as e:
                print(f"[TTS] espeak-ng error: {e}")
                return None

            if os.path.exists(tmp_path):
                audio = Path(tmp_path).read_bytes()
                os.unlink(tmp_path)
                return audio
        except Exception as e:
            print(f"[TTS] Fallback espeak falló: {e}")
        return None

    # ══════════════════════════════════════════════════════════
    #  SÍNTESIS EN FRAGMENTOS (streaming)
    # ══════════════════════════════════════════════════════════

    async def synthesize_streaming(self, text: str, speed: Optional[float] = None):
        """
        Genera audio por fragmentos para respuestas largas.
        Divide por oraciones para empezar a reproducir antes
        de que termine la síntesis completa.
        """
        sentences = self._split_sentences(text)
        for sentence in sentences:
            if not sentence.strip():
                continue
            audio = await self.synthesize(sentence.strip(), speed=speed)
            if audio:
                yield audio

    def _split_sentences(self, text: str) -> list:
        """Divide texto en oraciones para síntesis parcial."""
        import re
        # Dividir por punto, signo de exclamación, pregunta
        sentences = re.split(r'(?<=[.!?])\s+', text)
        # Agrupar oraciones cortas para no generar demasiados fragmentos
        result, current = [], ""
        for s in sentences:
            current += " " + s
            if len(current) > 150:
                result.append(current.strip())
                current = ""
        if current.strip():
            result.append(current.strip())
        return result

    # ══════════════════════════════════════════════════════════
    #  LIMPIEZA DE TEXTO
    # ══════════════════════════════════════════════════════════

    def _clean_for_tts(self, text: str) -> str:
        """
        Limpia el texto para síntesis de voz.
        Elimina markdown, código, URLs y caracteres especiales.
        """
        import re

        # Eliminar bloques de código
        text = re.sub(r'```[\s\S]*?```', 'código adjunto.', text)
        text = re.sub(r'`[^`]+`', '', text)

        # Eliminar URLs
        text = re.sub(r'https?://\S+', '', text)

        # Eliminar markdown
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # bold
        text = re.sub(r'\*(.+?)\*',     r'\1', text)  # italic
        text = re.sub(r'#{1,6}\s',      '',    text)  # headers
        text = re.sub(r'^\s*[-•]\s*',   '',    text, flags=re.MULTILINE)  # bullets
        text = re.sub(r'^\s*\d+\.\s*',  '',    text, flags=re.MULTILINE)  # numbered

        # Eliminar emojis
        text = re.sub(
            r'[\U00010000-\U0010ffff]|[\U0001F600-\U0001F64F]|'
            r'[\U0001F300-\U0001F5FF]|[\U0001F680-\U0001F6FF]|'
            r'[\U0001F1E0-\U0001F1FF]', '', text
        )

        # Limpiar espacios múltiples y saltos de línea
        text = re.sub(r'\n+', '. ', text)
        text = re.sub(r'\s+', ' ', text)

        # v3.0: Naturalización Premium (Mejora de pausas)
        text = text.replace(";", ".").replace(" - ", ", ")
        
        return text.strip()

    # ══════════════════════════════════════════════════════════
    #  ESTADO Y CONFIGURACIÓN
    # ══════════════════════════════════════════════════════════

    def get_status(self) -> dict:
        """Estado actual del motor de voz."""
        piper_voices = [
            f.stem for f in VOICE_DIR.glob("*.onnx")
        ]
        # Siempre añadir las opciones nativas de Piper si no están descargadas aún
        default_piper = ["es_AR-daniela-high", "es_ES-sharvard-medium", "es_MX-ald-medium", "es_ES-davefx-medium"]
        for v in default_piper:
            if v not in piper_voices:
                piper_voices.append(v)
                
        cache_size = sum(
            f.stat().st_size for f in CACHE_DIR.glob("*.wav")
        ) // 1024  # KB
        
        # mp3 también para edge-tts
        cache_size += sum(
            f.stat().st_size for f in CACHE_DIR.glob("*.mp3")
        ) // 1024

        return {
            "ready":            self._ready,
            "current_voice":    self._model_name,
            "engine":           self.engine or "unknown",

            "kokoro_voices":    KOKORO_VOICES,
            "piper_voices":     list(set(piper_voices)),
            "edge_voices":      EDGE_VOICES,
            "cache_entries":    len(list(CACHE_DIR.glob("*.wav"))) + len(list(CACHE_DIR.glob("*.mp3"))),
            "cache_size_kb":    cache_size,
            "piper_installed":  self._check_piper(),
            "espeak_available": self._check_espeak(),
        }

    def _check_piper(self) -> bool:
        try:
            import piper  # type: ignore
            return True
        except ImportError:
            return False

    def _check_espeak(self) -> bool:
        import shutil
        return shutil.which("espeak-ng") is not None

    def set_voice(self, voice_name: str):
        """
        Cambiar la voz de NOVA.
        Detecta automáticamente el motor (Kokoro, Edge-TTS, Piper) según el nombre.
        """
        if self._model_name == voice_name:
            return  # Evitar reinicialización si es la misma voz

        old_engine = self.engine
        self._model_name = voice_name
        self._voice = None
        self._ready = False
        self._loading = False  # Asegurar que no quede bloqueado

        # Pre-detectar el motor para que initialize() lo recoja
        kokoro_prefixes = ("af_", "am_", "bf_", "bm_", "ef_", "em_", "ff_", "if_", "im_", "jf_", "jm_", "pf_", "pm_", "zf_", "zm_")
        if voice_name.startswith(kokoro_prefixes):
            self.engine = None  # Se asignará en initialize()
        elif voice_name.endswith("Neural"):
            self.engine = None
        else:
            self.engine = None

        print(f"[TTS] Voz cambiada a: {voice_name} (motor anterior: {old_engine}) - se cargará en la próxima síntesis")

    def clear_cache(self):
        """Limpiar caché de audio."""
        for f in CACHE_DIR.glob("*.wav"):
            f.unlink()
        for f in CACHE_DIR.glob("*.mp3"):
            f.unlink()
        print("[TTS] Caché de audio limpiado")

    def shutdown(self):
        """Detener y liberar el pool de procesos de síntesis Kokoro."""
        global _kokoro_pool
        if _kokoro_pool is not None:
            try:
                _kokoro_pool.shutdown(wait=False, cancel_futures=True)
                print("[TTS] Pool de procesos Kokoro liberado.")
            except Exception as e:
                print(f"[TTS] Error liberando pool Kokoro: {e}")
            finally:
                _kokoro_pool = None


# Instancia global — la voz de NOVA
nova_voice = NOVAVoiceEngine()