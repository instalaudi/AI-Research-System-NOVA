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
from pathlib import Path
from typing import Optional


# ── Directorio de caché de voces ─────────────────────────────────
VOICE_DIR   = Path("data/tts_voices")
CACHE_DIR   = Path("data/tts_cache")
VOICE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Voz por defecto de NOVA ───────────────────────────────────────
DEFAULT_VOICE   = os.getenv("NOVA_VOICE", "es_MX-claude-high")
DEFAULT_SPEAKER = 0
DEFAULT_SPEED   = float(os.getenv("NOVA_VOICE_SPEED", "1.0"))


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

    # ══════════════════════════════════════════════════════════
    #  INICIALIZACIÓN
    # ══════════════════════════════════════════════════════════

    async def initialize(self, voice_name: Optional[str] = None) -> bool:
        """Inicializa el motor de voz de NOVA."""
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
        voice = voice_name or self._model_name

        try:
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
                print(f"[TTS] ✅ Voz de NOVA lista: {voice}")
                return True
            else:
                print(f"[TTS] ❌ No se pudo cargar la voz {voice}")
                return False

        except ImportError:
            print("[TTS] ⚠ Piper no instalado. Ejecuta: pip install piper-tts")
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
                        print(f"[TTS] ✅ {fname} descargado ({len(r.content)//1024}KB)")
                    else:
                        print(f"[TTS] ⚠ Error descargando {fname}: HTTP {r.status_code} desde {url}")

        except Exception as e:
            print(f"[TTS] Error descargando voz: {e}")

    # ══════════════════════════════════════════════════════════
    #  SÍNTESIS DE VOZ
    # ══════════════════════════════════════════════════════════

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
        cache_key  = hashlib.md5(f"{clean_text}{speed}{speaker}".encode()).hexdigest()
        cache_file = CACHE_DIR / f"{cache_key}.wav"
        if self._use_cache and cache_file.exists():
            return cache_file.read_bytes()

        # Asegurar que el motor está listo
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
                    
                    # Extraer solo los frames (saltando el header de 44 bytes de WAV)
                    # Silenciamos error de slicing de bytes (falso positivo de Pyre2)
                    pcm_data = chunk_buf.getvalue()[44:] # type: ignore
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
            await proc.wait()

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
        voices_available = [
            f.stem for f in VOICE_DIR.glob("*.onnx")
        ]
        cache_size = sum(
            f.stat().st_size for f in CACHE_DIR.glob("*.wav")
        ) // 1024  # KB

        return {
            "ready":            self._ready,
            "current_voice":    self._model_name,
            "voices_available": voices_available,
            "cache_entries":    len(list(CACHE_DIR.glob("*.wav"))),
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
        """Cambiar la voz de NOVA."""
        self._model_name = voice_name
        self._voice      = None
        self._ready      = False
        print(f"[TTS] Voz cambiada a: {voice_name} — se cargará en la próxima síntesis")

    def clear_cache(self):
        """Limpiar caché de audio."""
        for f in CACHE_DIR.glob("*.wav"):
            f.unlink()
        print("[TTS] Caché de audio limpiado")


# Instancia global — la voz de NOVA
nova_voice = NOVAVoiceEngine()